// HoFi Protocol — Middleware de Edge para protección de rutas
//
// Intercepta requests antes de que lleguen a los Route Handlers.
// Solo protege las rutas que requieren autenticación obligatoria.
// Las rutas públicas (guest) pasan sin verificación.
//
// Rutas protegidas (requieren sesión):
//   - /api/user/me
//   - /api/user/transactions
//
// Rutas públicas (no requieren sesión):
//   - /api/holon/*/           (stats agregados, visibles a todos)
//   - /api/holon/*/feed       (los Route Handlers aplican máscara por rol)
//   - /api/holon/*/yield      (métricas del holón, públicas)
//   - /api/world/holons       (mapa mundial, público)
//   - /api/care/register      (los Route Handlers aplican lógica de sesión)
//   - /api/auth/*             (login, voice auth, logout)

import { NextRequest, NextResponse } from "next/server";
import { verifySessionToken } from "@/lib/server/auth";

// Rutas que requieren sesión obligatoria
const PROTECTED_PATHS = ["/api/user/me", "/api/user/transactions"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Verificar si la ruta está protegida
  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  // Leer cookie de sesión
  const token = req.cookies.get("hofi_session")?.value;
  if (!token) {
    return NextResponse.json(
      { error: "No autenticado — se requiere sesión activa" },
      { status: 401 }
    );
  }

  // Verificar JWT
  const session = await verifySessionToken(token);
  if (!session) {
    return NextResponse.json(
      { error: "Sesión expirada o inválida" },
      { status: 401 }
    );
  }

  // Pasar la identidad verificada al Route Handler via headers
  // (evita re-verificar el JWT dentro del handler)
  const headers = new Headers(req.headers);
  headers.set("x-hofi-user-id", session.userId);
  headers.set("x-hofi-user-name", session.name);
  headers.set("x-hofi-user-role", session.role);
  headers.set("x-hofi-holon-id", session.holonId);

  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Solo ejecutar el middleware en rutas /api/*
  // Excluir assets estáticos y _next
  matcher: ["/api/:path*"],
};
