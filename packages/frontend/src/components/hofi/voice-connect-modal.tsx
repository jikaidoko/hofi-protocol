"use client";

import { useState, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Mic, Mail, Lock, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UserSession } from "@/lib/mock-data";

interface VoiceConnectModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConnect: (session: UserSession) => void;
}

type AuthMethod = "voice" | "traditional";

// Estados del flujo de voz: ayuda al usuario a entender qué está pasando
// (antes mostraba "Listening for 3 seconds…" durante todo el tiempo, incluso
// mientras el backend verificaba el embedding — daba sensación de cuelgue).
type VoicePhase = "idle" | "recording" | "submitting";

/** Fetch the current session from the server (reads the httpOnly cookie). */
async function fetchSession(): Promise<UserSession> {
  const res = await fetch("/api/user/me", { credentials: "include" });
  if (!res.ok) throw new Error("Could not load session");
  const data = await res.json();
  return {
    userId: data.userId ?? data.sub ?? `user_${Date.now()}`,
    name: data.name ?? data.email ?? "Member",
    role: data.role ?? "member",
    holonId: data.holonId ?? "familia-mourino",
    balance: data.balance ?? 0,
    avatar: (data.name ?? data.email ?? "M").substring(0, 2).toUpperCase(),
  };
}

export function VoiceConnectModal({
  open,
  onOpenChange,
  onConnect,
}: VoiceConnectModalProps) {
  const [authMethod, setAuthMethod] = useState<AuthMethod>("voice");
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Refs for voice recording
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Waveform bars (static — just for animation)
  const bars = Array(12).fill(0);

  // ─── Voice Auth ────────────────────────────────────────────────────────────

  const handleStartListening = async () => {
    setError(null);

    // Request microphone access
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access denied. Please allow mic access and try again.");
      return;
    }

    setVoicePhase("recording");
    audioChunksRef.current = [];

    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      // Stop all mic tracks
      stream.getTracks().forEach((t) => t.stop());

      // Apenas paramos de grabar pasamos a "Processing…" para que el usuario
      // entienda que el audio ya está siendo verificado contra los embeddings.
      setVoicePhase("submitting");

      const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
      await submitVoiceAuth(audioBlob);
    };

    // Record for 3 seconds then stop automatically
    recorder.start();
    setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, 3000);
  };

  const submitVoiceAuth = async (audioBlob: Blob) => {
    try {
      const form = new FormData();
      form.append("audio", audioBlob, "voice.webm");

      const res = await fetch("/api/auth/voice", {
        method: "POST",
        credentials: "include",
        body: form,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.error ?? `Auth failed (${res.status})`);
      }

      // Server set the httpOnly cookie — now load the real session
      const session = await fetchSession();
      onConnect(session);
      onOpenChange(false);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Voice authentication failed");
    } finally {
      setVoicePhase("idle");
    }
  };

  // ─── Email / Password Auth ─────────────────────────────────────────────────

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !password) {
      setError("Please enter email and password");
      return;
    }

    setIsSubmitting(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.error ?? `Login failed (${res.status})`);
      }

      // Server set the cookie — load real session
      const session = await fetchSession();
      onConnect(session);
      onOpenChange(false);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Check credentials.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // ─── Social / OAuth ────────────────────────────────────────────────────────

  const handleSocialLogin = (provider: "google" | "telegram" | "x") => {
    // Redirect to OAuth flow — server will redirect back to / after auth
    window.location.href = `/api/auth/oauth/${provider}`;
  };

  // ─── Utils ─────────────────────────────────────────────────────────────────

  const resetForm = () => {
    setEmail("");
    setPassword("");
    setError(null);
    setVoicePhase("idle");
    setIsSubmitting(false);
    setAuthMethod("voice");
    audioChunksRef.current = [];
    mediaRecorderRef.current = null;
  };

  const handleClose = () => {
    // Stop any active recording
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    resetForm();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md bg-card border-border/30">
        <DialogHeader>
          <DialogTitle className="text-center">Connect to HoFi</DialogTitle>
          <DialogDescription className="text-center">
            Authenticate to access your holonic community
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Auth Method Tabs */}
          <div className="flex rounded-lg bg-muted/30 p-1">
            <button
              onClick={() => { setAuthMethod("voice"); setError(null); }}
              className={cn(
                "flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all",
                authMethod === "voice"
                  ? "bg-card shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Mic className="h-4 w-4 inline mr-1.5" />
              Voice
            </button>
            <button
              onClick={() => { setAuthMethod("traditional"); setError(null); }}
              className={cn(
                "flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all",
                authMethod === "traditional"
                  ? "bg-card shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Mail className="h-4 w-4 inline mr-1.5" />
              Email
            </button>
          </div>

          {/* ── Voice Auth ── */}
          {authMethod === "voice" && (
            <div className="flex flex-col items-center gap-6">
              <div className="relative">
                <button
                  onClick={handleStartListening}
                  disabled={voicePhase !== "idle"}
                  className={cn(
                    "relative h-28 w-28 rounded-full transition-all duration-300",
                    "flex items-center justify-center",
                    voicePhase === "recording"
                      ? "bg-primary/20 scale-105"
                      : voicePhase === "submitting"
                      ? "bg-primary/30 scale-105 cursor-default"
                      : "bg-muted hover:bg-muted/80 hover:scale-105"
                  )}
                >
                  {voicePhase === "recording" && (
                    <>
                      <span className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
                      <span className="absolute inset-2 rounded-full bg-primary/30 animate-pulse" />
                    </>
                  )}
                  {voicePhase === "submitting" ? (
                    <Loader2 className="h-12 w-12 relative z-10 text-primary animate-spin" />
                  ) : (
                    <Mic
                      className={cn(
                        "h-12 w-12 relative z-10 transition-colors",
                        voicePhase === "recording"
                          ? "text-primary"
                          : "text-muted-foreground"
                      )}
                    />
                  )}
                </button>

                {/* Waveform — solo durante recording */}
                {voicePhase === "recording" && (
                  <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 flex items-end gap-0.5 h-6">
                    {bars.map((_, i) => (
                      <div
                        key={i}
                        className="w-1 bg-primary rounded-full animate-[listening-bounce_0.6s_ease-in-out_infinite]"
                        style={{ height: "16px", animationDelay: `${i * 0.05}s` }}
                      />
                    ))}
                  </div>
                )}
              </div>

              <div className="text-center mt-4">
                <p className="text-sm font-medium">
                  {voicePhase === "recording"
                    ? "Listening for 3 seconds…"
                    : voicePhase === "submitting"
                    ? "Processing…"
                    : "Tap to speak your name"}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {voicePhase === "submitting"
                    ? "Verifying your voice signature"
                    : "Your voice identifies you to the community"}
                </p>
              </div>

              {error && (
                <p className="text-sm text-destructive text-center">{error}</p>
              )}
            </div>
          )}

          {/* ── Email / Password Auth ── */}
          {authMethod === "traditional" && (
            <div className="space-y-4">
              <form onSubmit={handleEmailLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm">Email</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-10 bg-muted/30 border-border/50"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm">Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="password"
                      type="password"
                      placeholder="Enter your password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10 bg-muted/30 border-border/50"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}

                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Connecting…
                    </>
                  ) : (
                    "Connect"
                  )}
                </Button>
              </form>

              {/* Divider */}
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-border/50" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">
                    or continue with
                  </span>
                </div>
              </div>

              {/* Social Login */}
              <div className="grid grid-cols-3 gap-3">
                {/* Google */}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleSocialLogin("google")}
                  disabled={isSubmitting}
                  className="h-11 bg-white hover:bg-gray-50 border-gray-300 text-gray-700"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                </Button>

                {/* Telegram */}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleSocialLogin("telegram")}
                  disabled={isSubmitting}
                  className="h-11 bg-[#0088cc] hover:bg-[#0077b5] border-[#0088cc] text-white"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
                  </svg>
                </Button>

                {/* X (Twitter) */}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleSocialLogin("x")}
                  disabled={isSubmitting}
                  className="h-11 bg-black hover:bg-gray-900 border-black text-white"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                  </svg>
                </Button>
              </div>

              <p className="text-xs text-center text-muted-foreground">
                Your identity is verified server-side. We never reveal who is in the holon.
              </p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
