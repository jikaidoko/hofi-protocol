// GET /api/auth/oauth/[provider]
// Inicia el flujo OAuth para Google, Telegram o X (Twitter).
//
// En esta versión, el flujo completo de OAuth no está implementado
// (requeriría CLIENT_ID / CLIENT_SECRET por proveedor y un callback URL).
// Este endpoint actúa como stub documentado listo para implementar.
//
// Proveedores planeados:
//   - google:   OAuth2 PKCE con Google Identity Platform
//   - telegram:  Telegram Login Widget (hash verificado con bot token)
//   - x:        OAuth2 PKCE con Twitter API v2

import { NextRequest, NextResponse } from "next/server";

type Provider = "google" | "telegram" | "x";

const SUPPORTED_PROVIDERS: Provider[] = ["google", "telegram", "x"];

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  const { provider } = await params;

  if (!SUPPORTED_PROVIDERS.includes(provider as Provider)) {
    return NextResponse.json(
      { error: `Proveedor '${provider}' no soportado` },
      { status: 400 }
    );
  }

  // ── Google OAuth2 ──────────────────────────────────────────────────────────
  if (provider === "google") {
    const clientId = process.env.GOOGLE_CLIENT_ID;
    if (!clientId) {
      return NextResponse.json(
        { error: "GOOGLE_CLIENT_ID no configurado" },
        { status: 501 }
      );
    }
    const redirectUri = `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/oauth/google/callback`;
    const scope = "openid email profile";
    const state = crypto.randomUUID();
    const googleUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    googleUrl.searchParams.set("client_id", clientId);
    googleUrl.searchParams.set("redirect_uri", redirectUri);
    googleUrl.searchParams.set("response_type", "code");
    googleUrl.searchParams.set("scope", scope);
    googleUrl.searchParams.set("state", state);
    return NextResponse.redirect(googleUrl.toString());
  }

  // ── Telegram Login Widget ──────────────────────────────────────────────────
  // Telegram usa un widget JS que llama a un callback URL con hash verificado.
  // El bot token se usa para verificar la firma (igual que en bot.py).
  if (provider === "telegram") {
    const botUsername = process.env.TELEGRAM_BOT_USERNAME ?? "HoFiBot";
    const callbackUrl = encodeURIComponent(
      `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/oauth/telegram/callback`
    );
    // Redirigir a una página intermedia que muestra el widget de Telegram
    return NextResponse.redirect(
      `/auth/telegram-widget?bot=${botUsername}&callback=${callbackUrl}`
    );
  }

  // ── X / Twitter OAuth2 ────────────────────────────────────────────────────
  if (provider === "x") {
    const clientId = process.env.X_CLIENT_ID;
    if (!clientId) {
      return NextResponse.json(
        { error: "X_CLIENT_ID no configurado" },
        { status: 501 }
      );
    }
    const redirectUri = `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/oauth/x/callback`;
    const xUrl = new URL("https://twitter.com/i/oauth2/authorize");
    xUrl.searchParams.set("response_type", "code");
    xUrl.searchParams.set("client_id", clientId);
    xUrl.searchParams.set("redirect_uri", redirectUri);
    xUrl.searchParams.set("scope", "users.read tweet.read");
    xUrl.searchParams.set("state", crypto.randomUUID());
    xUrl.searchParams.set("code_challenge", "challenge");
    xUrl.searchParams.set("code_challenge_method", "plain");
    return NextResponse.redirect(xUrl.toString());
  }

  return NextResponse.json({ error: "Proveedor no implementado" }, { status: 501 });
}
