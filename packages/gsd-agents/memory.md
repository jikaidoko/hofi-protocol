## GSD-005 â€” BLOQUEADO (3/3 reintentos) Â· 18min 31s
Tarea: Rate limiting con Redis en /evaluar
Causa raÃ­z: Constructor genera rate_limiter.py > 8000 tokens â†’ truncado â†’ Auditor no puede auditar cÃ³digo incompleto
LecciÃ³n: Redis + trusted proxies + X-Forwarded-For = demasiado complejo para un bloque atÃ³mico
Siguiente: simplificar a in-memory sin Redis

## GSD-006 â€” BLOQUEADO (3/3 reintentos) Â· 12min 59s
Tarea: Rate limiting en memoria sin Redis
Bloqueos detectados:
  - Race condition en check_rate_limit() bajo carga concurrente (asyncio sin Lock)
  - Memory exhaustion via IP rotation (dict sin lÃ­mite de tamaÃ±o)
  - Race condition en global_request_count
LecciÃ³n: Implementar rate limiting correcto a mano en Python es complejo y el Auditor conoce todos los vectores
Siguiente: usar slowapi (librerÃ­a estÃ¡ndar FastAPI) que resuelve thread-safety internamente

## Deuda de seguridad acumulada (bloques GSD futuros obligatorios)
- [ALTA] Sin autenticaciÃ³n en endpoints /evaluar y /orquestador
- [ALTA] Headers HTTP de seguridad ausentes (X-Content-Type-Options, X-Frame-Options, HSTS)
- [ALTA] Sin validaciÃ³n de tamaÃ±o mÃ¡ximo en inputs (memory exhaustion)
- [ALTA] CORS no configurado restrictivamente
- [MEDIA] Logs sin request_id para correlaciÃ³n
- [MEDIA] Dependencies sin hash pinning en requirements.txt
- [MEDIA] Sin health check de dependencias externas (Gemini API) en /health

## Stack actual
- Tenzo v0.4.0 â†’ :8080 (FastAPI + Docker, DB_MOCK=true)
- Orquestador v0.1.0 â†’ :8090 (FastAPI + Docker)
- Modelo Gemini: gemini-2.5-flash
- Red Docker: hofi-net
- Sistema GSD automatizado: 6 agentes Claude SDK operativos

## Entorno desarrollo
- Windows 11, PowerShell, Docker Desktop
- Python 3.13
- Carpeta: C:\dev\AIProgrammingAgentTeam
- Servicios en C:\dev\hofi-gsd-004


## Deuda de seguridad â€” GSD-007: rate limiting en /evaluar usando slowapi, maximo 10 req/min por IP, thread-safe, con limite maximo de 10000 entradas en memoria â€” 2026-03-20 20:36
- [ALTA] Rate limiting se aplica DESPUÃ‰S de parsing de JSON en /evaluar â†’ GSD futuro obligatorio
- [ALTA] Falta validaciÃ³n de Content-Type antes de rate limit â†’ GSD futuro obligatorio
- [ALTA] Headers X-RateLimit-* expuestos en responses de error 500 â†’ GSD futuro obligatorio
- [ALTA] Sin rate limit secundario para IPs que exceden lÃ­mite frecuentemente â†’ GSD futuro obligatorio
- [MEDIA] Storage no tiene TTL, entradas de IPs inactivas nunca expiran â†’ GSD futuro obligatorio
- [MEDIA] Tests no verifican comportamiento bajo carga sostenida (>1000 req/s) â†’ GSD futuro obligatorio
- [MEDIA] Dockerfile instala dependencias en runtime, no usa multi-stage build â†’ GSD futuro obligatorio
- [MEDIA] Health check en Dockerfile no verifica rate limiting funcional â†’ GSD futuro obligatorio
- [BAJA] rate_limiter.py deprecado pero no marcado para eliminaciÃ³n â†’ GSD futuro obligatorio
- [BAJA] .env.example no documenta TRUST_PROXY_LIST requerido â†’ GSD futuro obligatorio
- [BAJA] Sin logging estructurado (JSON) para anÃ¡lisis forense â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-007: rate limiting en /evaluar usando slowapi, maximo 10 req/min por IP, thread-safe, con limite maximo de 10000 entradas en memoria â€” 2026-03-20 20:39
- [ALTA] Falta circuit breaker pattern en limiter para prevenir cascading failures â†’ GSD futuro obligatorio
- [ALTA] Logs con hashed IPs no incluyen request_id para correlaciÃ³n forense â†’ GSD futuro obligatorio
- [ALTA] TRUST_PROXY_LIST no soporta CIDR ranges, solo IPs individuales â†’ GSD futuro obligatorio
- [ALTA] Content-Length no validado antes de rate limiting, vulnerable a slowloris â†’ GSD futuro obligatorio
- [MEDIA] Rate limiter usa decorator que no permite bypass para health checks â†’ GSD futuro obligatorio
- [MEDIA] Headers X-RateLimit-* no incluyen nombre del rate limit aplicado (ambiguedad con mÃºltiples limits) â†’ GSD futuro obligatorio
- [MEDIA] Falta monitoreo de mÃ©tricas de rate limiting (Prometheus/StatsD) â†’ GSD futuro obligatorio
- [MEDIA] Tests no verifican comportamiento bajo race conditions reales (GIL puede ocultar bugs) â†’ GSD futuro obligatorio
- [MEDIA] Emergency mode threshold hardcoded (9500), deberÃ­a ser configurable â†’ GSD futuro obligatorio
- [BAJA] OrderedDict.move_to_end() causa O(n) traversal bajo lock en CPython <3.8 â†’ GSD futuro obligatorio
- [BAJA] Retry-After header siempre retorna 60 (hardcoded), deberÃ­a calcular tiempo real hasta window reset â†’ GSD futuro obligatorio
- [BAJA] Falta documentaciÃ³n de rate limits en OpenAPI schema (Swagger UI no muestra lÃ­mites) â†’ GSD futuro obligatorio
- [BAJA] ThreadSafeStorage no expone mÃ©tricas internas (hit rate, eviction count) para debugging â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-008: agregar slowapi al tenzo_agent.py existente, solo decorador @limiter.limit en /evaluar, 10 req/min, sin tocar infraestructura â€” 2026-03-20 20:55
- [ALTA] DUPLICACIÃ“N DE RATE LIMITING - Existe infraestructura de rate limiting en app.py (mencionada en notas_seguridad) y ahora slowapi en /evaluar. No hay evidencia de coordinaciÃ³n: Â¿cuÃ¡l se ejecuta primero? Â¿Se suman los lÃ­mites o colisionan? Test C5 verifica que /health no tiene rate limit de slowapi pero no prueba interacciÃ³n con sistema global â†’ GSD futuro obligatorio
- [ALTA] SIN VALIDACIÃ“N DE ORDEN DE DECORADORES - FastAPI ejecuta decoradores en orden inverso. Si @limiter.limit estÃ¡ despuÃ©s de @app.post, el rate limiting se aplica DESPUÃ‰S de parsear JSON body con Pydantic. Payload malicioso de 100MB pasa validaciÃ³n de tamaÃ±o antes de rate limit â†’ DoS bypass â†’ GSD futuro obligatorio
- [MEDIA] LOGS SIN HASH DE IP - Nota de seguridad dice 'IP hasheada no plaintext' pero cÃ³digo truncado muestra logger.info genÃ©rico. Si slowapi loggea IPs en plaintext, viola compliance de privacidad (GDPR, CCPA requieren minimizaciÃ³n de datos) â†’ GSD futuro obligatorio
- [MEDIA] TEST INCOMPLETO DE RETRY-AFTER - C2 verifica que request 11 retorna 429 con X-RateLimit-Remaining: 0 pero no valida header Retry-After (RFC 6585). Cliente no sabe cuÃ¡ndo reintentar â†’ UX degradada o retry storms â†’ GSD futuro obligatorio
- [MEDIA] SIN WHITELIST DE IPS INTERNAS - Health checks desde orquestador (:8090) o monitoreo interno consumen rate limit de /evaluar si usan misma IP pÃºblica tras NAT. Puede causar falsos positivos en alertas â†’ GSD futuro obligatorio
- [BAJA] DEPENDENCIAS SIN PINNING COMPLETO - requirements.txt tiene versiones exactas (fastapi==0.115.12) pero sus dependencias transitivas no estÃ¡n fijadas. slowapi depende de limits que depende de deprecated con vulnerabilidades conocidas en versiones antiguas â†’ GSD futuro obligatorio
- [BAJA] SIN MÃ‰TRICAS DE RATE LIMITING - No hay instrumentaciÃ³n para ver cuÃ¡ntos requests son rechazados por rate limit (SLO de disponibilidad), distribuciÃ³n de IPs top (detecciÃ³n de DDoS), o tasa de falsos positivos. Debugging de incidentes es ciego â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-008: agregar slowapi al tenzo_agent.py existente, solo decorador @limiter.limit en /evaluar, 10 req/min, sin tocar infraestructura â€” 2026-03-20 20:58
- [ALTA] Dockerfile con --workers 1 bloquea escalado horizontal â†’ GSD futuro obligatorio
- [MEDIA] Sin mÃ©tricas de rate limiting para detecciÃ³n de abuse â†’ GSD futuro obligatorio
- [ALTA] X-Forwarded-For sin validaciÃ³n de formato â†’ GSD futuro obligatorio
- [ALTA] Rate limiting solo en /evaluar, /orquestador sin protecciÃ³n â†’ GSD futuro obligatorio
- [MEDIA] Sin TTL en storage in-memory, IPs ocupan memoria hasta restart â†’ GSD futuro obligatorio
- [BAJA] Retry-After header hardcoded a 60s â†’ GSD futuro obligatorio
- [MEDIA] Sin documentaciÃ³n de limitaciones de rate limiting in-memory â†’ GSD futuro obligatorio
- [MEDIA] Dependencies sin version pinning exacto (usa >= en lugar de ==) â†’ GSD futuro obligatorio
- [ALTA] Sin validaciÃ³n de tamaÃ±o mÃ¡ximo en RequestBody de /evaluar â†’ GSD futuro obligatorio
- [ALTA] CORS no configurado, permite requests desde cualquier origen â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-008: agregar slowapi al tenzo_agent.py existente, solo decorador @limiter.limit en /evaluar, 10 req/min, sin tocar infraestructura â€” 2026-03-20 21:00
- [MEDIA] validate_trusted_proxies() solo loggea warning si TRUST_PROXY_LIST vacÃ­a pero continÃºa ejecuciÃ³n - bajo deployment real sin proxy reverso, todo request usa IP directa sin protecciÃ³n â†’ GSD futuro obligatorio
- [BAJA] Limiter inicializado sin default_limits global - cada endpoint debe decorarse manualmente, fÃ¡cil olvidar endpoints futuros â†’ GSD futuro obligatorio
- [MEDIA] ipaddress.ip_address(ip).is_private puede lanzar ValueError si IP malformada - validate_trusted_proxies() no tiene try/except â†’ GSD futuro obligatorio
- [BAJA] rate_limit_handler loggea exception pero no loggea request metadata (user-agent, referer) Ãºtil para anÃ¡lisis forense â†’ GSD futuro obligatorio
- [ALTA] Criterio C3 requiere validar 8.8.8.8 como IP pÃºblica pero cÃ³digo solo valida .is_private - no rechaza IPs pÃºblicas explÃ­citamente con ValueError custom â†’ GSD futuro obligatorio
- [MEDIA] requirements.txt sin hash pinning (==version vs ==version --hash sha256:...) - supply chain attack via PyPI compromise â†’ GSD futuro obligatorio
- [ALTA] /evaluar endpoint falta - tenzo_agent.py truncado en auditorÃ­a, imposible verificar @limiter.limit('10/minute') aplicado correctamente â†’ GSD futuro obligatorio
- [BAJA] Startup no valida que slowapi instalada correctamente - import podrÃ­a fallar silenciosamente si requirements.txt no ejecutado â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-009: agregar slowapi al tenzo_agent.py existente, decorador en /evaluar, 10 req/min, retornar headers X-RateLimit-Limit y X-RateLimit-Remaining â€” 2026-03-20 21:08
- [ALTA] Falta validaciÃ³n de TRUST_PROXY_LIST como IP privadas en startup (mencionado en notas_seguridad) â†’ GSD futuro obligatorio
- [MEDIA] Falta test de race condition en rate limiting bajo carga concurrente â†’ GSD futuro obligatorio
- [MEDIA] Headers X-RateLimit-* pueden exponerse en error 500 (leak de estado interno) â†’ GSD futuro obligatorio
- [BAJA] Endpoint /health sin whitelist explÃ­cita puede consumir rate limit de orquestador â†’ GSD futuro obligatorio
- [BAJA] Falta logging estructurado de eventos de rate limiting para anÃ¡lisis de abuse â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-009: agregar slowapi al tenzo_agent.py existente, decorador en /evaluar, 10 req/min, retornar headers X-RateLimit-Limit y X-RateLimit-Remaining â€” 2026-03-20 21:10
- [BAJA] slowapi usa get_remote_address en imports pero key_func implementado con request.client.host - inconsistencia que puede causar confusiÃ³n en mantenimiento futuro â†’ GSD futuro obligatorio
- [MEDIA] verify_json_content_type dependency debe ejecutarse ANTES de rate limit para prevenir consumo de lÃ­mite con payloads maliciosos - cÃ³digo truncado no permite verificar orden de dependencies en decorator @app.post â†’ GSD futuro obligatorio
- [BAJA] get_client_ip() usa hash SHA256 truncado a 8 chars (2^32 posibles valores) para logging - colisiones posibles en datasets grandes. Considerar 16 chars (2^64) para reducir probabilidad de colisiÃ³n â†’ GSD futuro obligatorio
- [MEDIA] Falta logging explÃ­cito en startup '[RATE_LIMIT] Modo dev local: usando request.client.host (ignora X-Forwarded-For)' segÃºn criterio C4 - no se puede verificar sin ver cÃ³digo completo de startup â†’ GSD futuro obligatorio
- [BAJA] requirements.txt especifica deprecated>=1.2.14 para mitigar CVE-2022-21797 - buena prÃ¡ctica pero slowapi 0.1.9 puede tener otras dependencias transitivas desactualizadas. Considerar actualizar a slowapi>=0.2.0 cuando estÃ© disponible â†’ GSD futuro obligatorio
- [ALTA] Tests en test_rate_limiting.py usan TestClient que puede no simular request.client.host correctamente (valor None segÃºn riesgo identificado) - debe verificarse que tests realmente validan el fallback a '127.0.0.1' â†’ GSD futuro obligatorio
- [BAJA] Sin headers X-RateLimit-Reset en respuestas 429 - cliente no sabe cuÃ¡ndo window expira. slowapi no lo provee por defecto. Considerar custom handler segÃºn nota de seguridad BAJO â†’ GSD futuro obligatorio
- [MEDIA] Falta documentaciÃ³n en .env.example sobre key_func y WARNING de cambio futuro a get_remote_address con TRUST_PROXY_LIST cuando se agregue proxy reverso â†’ GSD futuro obligatorio
- [ALTA] RateLimitExceeded exception handler puede ser capturado por exception_handler global si existe - cÃ³digo truncado no permite verificar orden de registros en FastAPI. Verificar que _rate_limit_exceeded_handler se registra correctamente â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-009: agregar slowapi al tenzo_agent.py existente, decorador en /evaluar, 10 req/min, retornar headers X-RateLimit-Limit y X-RateLimit-Remaining â€” 2026-03-20 21:38
- [MEDIA] slowapi usa storage in-memory por defecto, rate limit se pierde al reiniciar contenedor y no funciona correctamente con mÃºltiples workers â†’ GSD futuro obligatorio
- [BAJA] get_remote_address en Docker Desktop siempre retorna 172.17.0.1, limitando por IP del gateway en vez de cliente real â†’ GSD futuro obligatorio
- [ALTA] CÃ³digo usa ellipsis (...) en lugar de mostrar implementaciÃ³n completa de modelos Pydantic y lÃ³gica de evaluaciÃ³n â†’ GSD futuro obligatorio
- [MEDIA] Sin manejo de excepciones especÃ­fico para errores de Google Generative AI (quota exceeded, invalid API key, timeouts) â†’ GSD futuro obligatorio
- [BAJA] Versiones exactas en requirements.txt sin permitir patches de seguridad (== en lugar de ~=) â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-009: agregar slowapi al tenzo_agent.py existente, decorador en /evaluar, 10 req/min, retornar headers X-RateLimit-Limit y X-RateLimit-Remaining â€” 2026-03-20 21:39
- [MEDIA] ValidaciÃ³n de API_KEY usa .strip() == '' pero no valida formato. Gemini API keys tienen formato especÃ­fico (AIza... con 39 caracteres). String no vacÃ­a pero invÃ¡lida pasarÃ­a validaciÃ³n â†’ GSD futuro obligatorio
- [MEDIA] slowapi en requirements.txt usa >=0.1.10 (versiÃ³n mÃ­nima) sin upper bound. VersiÃ³n 0.2.x puede tener breaking changes que rompan compatibilidad â†’ GSD futuro obligatorio
- [BAJA] Rate limit de 10/minute es muy restrictivo para endpoint de evaluaciÃ³n. Usuario legÃ­timo con 10 iteraciones de prompt en testing agota cuota en 1 minuto â†’ GSD futuro obligatorio
- [ALTA] CÃ³digo no muestra validaciÃ³n del modelo Pydantic para /evaluar. Falta confirmar que existe Field(..., max_length=X) en prompt para prevenir payloads gigantes â†’ GSD futuro obligatorio

## Deuda de seguridad â€” GSD-009: agregar slowapi al tenzo_agent.py existente, decorador en /evaluar, 10 req/min, retornar headers X-RateLimit-Limit y X-RateLimit-Remaining â€” 2026-03-20 21:41
- [ALTA] Rate limiting usa in-memory storage (threading.Lock) que no sincroniza entre workers de uvicorn. En producciÃ³n con mÃºltiples workers, cada proceso tiene su propio contador, permitiendo NÃ—limit requests/min donde N es el nÃºmero de workers. â†’ GSD futuro obligatorio
- [ALTA] get_remote_address() respeta X-Forwarded-For sin configurar trusted proxies. En desarrollo local no hay proxy, pero en deploy con nginx/cloudflare, un atacante puede spoof el header X-Forwarded-For para bypass del rate limit. â†’ GSD futuro obligatorio
- [MEDIA] Errores genai.types.GenerationError no distinguen entre errores de usuario (input invÃ¡lido) vs errores del sistema (API down, cuota excedida). Retornar siempre 500 dificulta debugging legÃ­timo y puede facilitar DoS si el atacante identifica inputs que agotan cuota. â†’ GSD futuro obligatorio
- [MEDIA] Ausencia de timeout explÃ­cito en llamadas a Gemini API. Si la API de Google tarda mÃ¡s de lo esperado, el request del cliente queda colgado hasta el timeout por defecto del servidor (posiblemente 60s+), facilitando ataques de agotamiento de recursos. â†’ GSD futuro obligatorio
- [ALTA] Campo 'contexto_adicional' permite hasta Field.max_length por defecto (sin lÃ­mite), pudiendo enviar payloads de MB de texto que consumen tokens de Gemini y generan costos elevados. Sin validaciÃ³n de tamaÃ±o, un atacante puede agotar cuota mensual con pocos requests. â†’ GSD futuro obligatorio
- [MEDIA] VersiÃ³n de google-generativeai==0.8.3 puede estar desactualizada. No hay proceso documentado para verificar CVEs en dependencias de IA que frecuentemente tienen vulnerabilidades de prompt injection o model hijacking. â†’ GSD futuro obligatorio

## GSD-013 completado — Tenzo en Cloud Run
URL: https://hofi-tenzo-381388570630.us-central1.run.app
DB: Cloud SQL PostgreSQL 18 en us-central1
DB_MOCK: false
Secrets: GEMINI_API_KEY y DB_PASS en Secret Manager



## Deuda de seguridad — GSD-014: agregar autenticacion JWT en tenzo_agent.py, endpoint /auth/token que genera token con SECRET_KEY, middleware que verifica Bearer token en /evaluar, retorna 401 si token invalido o ausente — 2026-03-21 13:56
- [BAJA] ACCESS_TOKEN_EXPIRE_MINUTES=60 hardcodeado, no configurable por entorno. En producción puede requerir valores diferentes según caso de uso → GSD futuro obligatorio
- [ALTA] python-jose==3.3.0 tiene vulnerabilidades conocidas (CVE-2024-33664). Última versión estable es 3.3.0 pero librería está deprecated a favor de python-jwt → GSD futuro obligatorio
- [ALTA] Endpoint /auth/token sin rate limiting permite ataques de fuerza bruta contra credenciales. 1000 intentos/segundo es factible → GSD futuro obligatorio
- [MEDIA] JWTError capturada pero mensaje genérico oculta información de debugging. En desarrollo puede dificultar troubleshooting de problemas de formato de token → GSD futuro obligatorio
- [MEDIA] Sin mecanismo de revocación de tokens. Token válido funciona hasta expiración incluso si usuario debe ser desautorizado inmediatamente → GSD futuro obligatorio
- [BAJA] HTTPBearer scheme sin realm ni description. Cliente recibe WWW-Authenticate vacío en 401 sin contexto → GSD futuro obligatorio

## Deuda de seguridad — GSD-014: agregar autenticacion JWT en tenzo_agent.py, endpoint /auth/token que genera token con SECRET_KEY, middleware que verifica Bearer token en /evaluar, retorna 401 si token invalido o ausente — 2026-03-21 13:58
- [MEDIA] Stack traces de errores JWT expuestos al cliente en HTTPException messages revelan estructura interna. JWTError exceptions deberían loguearse server-side pero retornar mensaje genérico al cliente. → GSD futuro obligatorio
- [BAJA] Token expiration de 15 minutos hardcodeado en código sin configuración. Para testing o casos de uso específicos puede requerirse ajuste sin redeployar. → GSD futuro obligatorio
- [MEDIA] Ausencia de refresh tokens obliga a re-autenticarse cada 15 minutos. Para clientes automatizados (scripts, CI/CD) es friction innecesario que puede llevar a almacenar credenciales inseguramente. → GSD futuro obligatorio
- [ALTA] Logging de intentos de autenticación fallidos ausente. No hay visibilidad de ataques brute force o intentos de acceso no autorizado para detección de incidentes. → GSD futuro obligatorio
- [BAJA] Username validator permite guiones y underscores pero no hay claridad en spec de negocio si son necesarios. Superficie de ataque innecesaria si solo se usa 'admin'. → GSD futuro obligatorio
- [MEDIA] python-jose dependency sin version pinning en cryptography. CVE futuras en cryptography pueden afectar validación de JWT sin rebuild explícito. → GSD futuro obligatorio
- [BAJA] Timezone handling usa timezone.utc pero no hay validación que sistema operativo del contenedor tenga timezone configurado correctamente. Puede causar drift en exp validation. → GSD futuro obligatorio

## Deuda de seguridad — GSD-014: agregar autenticacion JWT en tenzo_agent.py, endpoint /auth/token que genera token con SECRET_KEY, middleware que verifica Bearer token en /evaluar, retorna 401 si token invalido o ausente — 2026-03-21 14:00
- [ALTA] JWT_SECRET_KEY y ADMIN_PASSWORD en .env.example tienen placeholders vacíos pero sin validación al runtime. Si usuario deploya con valores vacíos, app debería fallar al inicio en vez de generar tokens inválidos. → GSD futuro obligatorio
- [ALTA] python-jose 3.3.0 tiene vulnerabilidad CVE-2024-33664 (algoritmo 'none' bypass) y CVE-2022-29217 (key confusion). Versión actual no recibe patches desde 2021. → GSD futuro obligatorio
- [MEDIA] passlib 1.7.4 no se usa en código provisto. Si no se usa bcrypt para hashear contraseñas adicionales (solo hay ADMIN_PASSWORD en plaintext en env), es dependencia innecesaria que aumenta superficie de ataque. → GSD futuro obligatorio
- [MEDIA] JWTMiddleware usa BaseHTTPMiddleware que tiene issues conocidos de performance y context propagation en FastAPI. Dependency injection con Depends() es patrón recomendado oficial. → GSD futuro obligatorio
- [ALTA] Código truncado no permite verificar manejo de excepciones en middleware. Si jwt.decode() lanza JWTError/ExpiredSignatureError sin try/except, leak de stack trace puede revelar JWT_SECRET_KEY parcial o estructura interna. → GSD futuro obligatorio
- [ALTA] Sin ver tenzo_agent.py completo, no se puede verificar si /auth/token está excluido de protected_paths en JWTMiddleware init. Si no está excluido, bootstrap problem: no se puede obtener token sin ya tener token. → GSD futuro obligatorio
- [BAJA] Token expiration de 24h es largo para desarrollo local donde no hay refresh token flow. Si token se compromete (ej: logs), es válido por día completo. → GSD futuro obligatorio

## M4.5 completado — GenLayer ISC deployado
TenzoEquityOracle: 0x6707c1a04dC387aD666758A392B43Aa0660DFECE
Network: GenLayer Studionet
Tx: 0xa16e9aa0cd1dcd60b2fe98fe1142f304dec320ebc5e4e7a0d0c3b4814b7c9235
