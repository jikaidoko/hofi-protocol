// POST /api/auth/logout
// Cierra la sesión limpiando la cookie httpOnly del servidor.

import { NextResponse } from "next/server";
import { clearCookieOptions } from "@/lib/server/auth";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(clearCookieOptions());
  return response;
}
