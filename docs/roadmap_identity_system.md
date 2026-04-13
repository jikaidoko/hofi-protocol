# HoFi Protocol — Roadmap: Sistema de Identidad On-Chain
## Voz → Dirección 0x → SBT GenLayer

**Versión:** 0.1 — Abril 2026  
**Objetivo:** Conectar la identidad biométrica de voz (bot Telegram) con la identidad soberana on-chain (GenLayer / HolonSBT), sin fricción para usuarios no técnicos y con soberanía opcional para usuarios Web3.

---

## Principio de diseño

> La voz de un miembro **es** su identidad en HoFi.  
> En la Fase 1 esa identidad se traduce a una wallet custodial transparente.  
> En la Fase 3 la voz **deriva** la wallet directamente — sin intermediarios, sin custodios.

La Opción B (wallet propia) no es una fase, es un **selector de modo** disponible desde Fase 1 para usuarios Web3. Las fases evolucionan la Opción A hacia la Opción C. La B coexiste en todas las fases.

---

## Fase 0 — Actual (manual)

**Estado:** ✅ En producción (limitado)

- El coordinator asigna manualmente la dirección 0x de cada miembro
- Las wallets existen independientemente del sistema de voz
- No hay conexión entre perfil de voz y dirección GenLayer
- Solo viable para holones pequeños con miembros técnicos

**Limitación:** No escala. Cada nuevo miembro requiere intervención manual del coordinator.

---

## Fase 1 — Wallets custodiales generadas en el registro de voz (Opción A)

**Target:** Q3 2026  
**Complejidad:** Media  
**Contrato afectado:** Ninguno (cambio de infraestructura backend)

### Qué cambia

Al completar el registro de voz en el bot Telegram, el sistema genera automáticamente un keypair EVM para el miembro:

```
Voz registrada → keypair generado → privateKey encriptada en Cloud SQL
                                  → publicAddress almacenado en perfil del miembro
                                  → SBT emitido automáticamente por Tenzo
```

### Componentes a desarrollar

1. **`wallet_service.py`** en el bot — genera keypair con `eth_account` al completar el registro de voz
2. **Columnas en Cloud SQL:** `wallet_address VARCHAR(42)`, `wallet_key_enc TEXT` (encriptada con KMS)
3. **Cloud KMS integration** — las claves privadas se encriptan con una clave maestra en Google KMS; nunca se almacenan en texto plano
4. **Auto-issue SBT** — tras el registro de voz exitoso, el Tenzo llama automáticamente a `issue_sbt()` usando la address generada
5. **`genlayer_bridge.py` update** — todas las transacciones on-chain del miembro se firman usando la clave custodial almacenada en KMS

### Interfaz de usuario

El miembro no ve wallets ni claves. Solo registra su voz y queda "dentro" del holón. Si en algún momento quiere exportar su clave privada (para usar su wallet independientemente), puede pedirla al coordinator.

### Opción B — modo Web3 (disponible desde Fase 1)

Durante la configuración del bot, antes de registrar la voz, el usuario puede elegir:

> "¿Querés usar tu propia wallet para aprobar transacciones?  
> [Sí, tengo MetaMask / Sí, tengo otra wallet] [No, el sistema lo maneja por mí]"

Si elige Sí → proporciona su dirección 0x → el sistema NO genera keypair custodial → el miembro firma sus propias transacciones desde su wallet externa.

```
Registro con wallet propia:
  bot → "Pegá tu dirección 0x" → valida checksum → guarda en perfil
  → SBT emitido a esa dirección
  → transacciones requieren firma externa del miembro
```

---

## Fase 2 — Portabilidad de identidad inter-holón

**Target:** Q4 2026  
**Dependencia:** Fase 1 completada

### Qué agrega

- Un miembro puede ser parte de múltiples holones con la misma identidad
- El SBT de un holón puede ser presentado como credencial en otro
- El registro de voz se hace una sola vez; la wallet custodial es la misma en todos los holones HoFi

### Componentes

1. **HolonSBT multi-holón** — un miembro tiene SBTs en contratos distintos pero misma address
2. **`verify_cross_holon_reputation()`** — función nueva en HolonSBT: dado un member_address y un holon_name externo, consulta su reputación en ese holón y la pondera en el cálculo local
3. **Registry de holones** — contrato simple que mapea `holon_name → holon_sbt_address` para que los holones puedan encontrarse mutuamente

---

## Fase 3 — Identidad derivada de la voz (Opción C / ZK)

**Target:** 2027  
**Dependencia:** Fase 1 completada + Semaphore/ZK research  
**Complejidad:** Alta  
**Alineado con:** HolonSBT v0.3.0 (diseñado, pendiente de implementación)

### Concepto

La identidad on-chain se **deriva determinísticamente del perfil de voz** sin exponer la voz:

```
Voz del miembro
  → embedding biométrico (vector numérico)
  → hash determinístico del embedding (semilla)
  → keypair EVM derivado de la semilla
  → ZK proof: "este keypair fue generado por una voz válida de este holón"
                sin revelar la voz ni el embedding
```

El resultado: la wallet del miembro ES su voz. Si pierde acceso al sistema, re-graba su voz → el mismo keypair emerge → recupera su identidad on-chain.

### Componentes a investigar y desarrollar

1. **Voice → deterministic seed:** normalizar el embedding de voz → hash estable bajo variaciones naturales del habla (misma persona, distinto día, distinto micrófono)
2. **Semaphore identity commitment:** el embedding procesado genera un `identityCommitment` en el protocolo Semaphore (no revela la voz)
3. **ZK proof de membresía:** el miembro puede demostrar "soy miembro de este holón" sin revelar su dirección ni su voz — solo el proof
4. **HolonSBT v0.3.0:** acepta `identityCommitment` como identificador en lugar de (o además de) dirección 0x

### Por qué la Opción C contiene a la A

En Fase 3, la clave privada sigue siendo custodial (el sistema la deriva y la usa), pero ya no es arbitraria — está ligada a la biometría. El usuario "no técnico" tiene la misma experiencia que en Fase 1, pero ahora su identidad es soberana y recuperable sin depender de que el backend guarde su clave.

La Opción B (wallet propia) sigue disponible — para usuarios Web3 que prefieren derivar ellos mismos su keypair o usar hardware wallets.

---

## Resumen de fases

| Fase | ¿Quién gestiona la clave? | Registro de voz | Complejidad | Target |
|------|--------------------------|-----------------|-------------|--------|
| 0 — Manual | Coordinator (manual) | Independiente | Baja | ✅ Hoy |
| 1 — Custodial | Sistema (KMS) | Auto-genera wallet | Media | Q3 2026 |
| 2 — Multi-holón | Sistema (KMS) | Portabilidad | Media | Q4 2026 |
| 3 — Voice-derived (ZK) | El propio miembro (biometría) | Voz = clave | Alta | 2027 |
| B — Wallet propia | El miembro (MetaMask) | Opcional en todas las fases | Baja | Fase 1+ |

