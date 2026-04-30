"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { X, Check, AlertCircle, Loader2 } from "lucide-react";

// Auto-stop de seguridad: si el usuario se olvida de tocar Done, paramos solos.
const AUTO_STOP_MS = 60_000;
// Cuánto tiempo dejamos visible el "✅ N HOCA" antes de cerrar el modal.
const SUCCESS_AUTOCLOSE_MS = 1_800;

type Phase = "idle" | "recording" | "submitting" | "success" | "error";

export interface CareResult {
  aprobada?: boolean;
  recompensa_hoca?: number;
  motivo?: string;
  razonamiento?: string;
  transcripcion?: string;
  [key: string]: unknown;
}

interface ListeningOverlayProps {
  active: boolean;
  onClose: () => void;
  onCareRegistered?: (result: CareResult) => void;
}

export function ListeningOverlay({
  active,
  onClose,
  onCareRegistered,
}: ListeningOverlayProps) {
  // Visualización
  const [bars, setBars] = useState<number[]>(Array(24).fill(0.3));
  const [mounted, setMounted] = useState(false);

  // Flujo de grabación
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<CareResult | null>(null);

  // Refs imperativas (no van a state porque no afectan el render)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const autoStopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Cleanup: liberar mic y timers cuando el overlay se cierra o el componente se desmonta.
  const cleanup = () => {
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    if (successTimerRef.current) {
      clearTimeout(successTimerRef.current);
      successTimerRef.current = null;
    }
    try {
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state !== "inactive"
      ) {
        mediaRecorderRef.current.stop();
      }
    } catch {
      // ignorar — ya estaba parado
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    chunksRef.current = [];
  };

  // Cuando el overlay se abre: arrancar grabación. Cuando se cierra: cleanup.
  useEffect(() => {
    if (!active) {
      cleanup();
      setPhase("idle");
      setErrorMsg(null);
      setResult(null);
      return;
    }

    // Iniciar grabación
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;

        const recorder = new MediaRecorder(stream);
        mediaRecorderRef.current = recorder;
        chunksRef.current = [];

        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
        };

        recorder.onstop = async () => {
          // No enviar si se canceló el flujo (el usuario cerró el modal).
          if (cancelled) return;

          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          chunksRef.current = [];

          if (blob.size < 1024) {
            setErrorMsg("La grabación es muy corta. Intentá de nuevo.");
            setPhase("error");
            return;
          }

          setPhase("submitting");
          await sendAudio(blob);
        };

        recorder.start();
        setPhase("recording");

        // Safety net: si el usuario se olvida de tocar Done.
        autoStopTimerRef.current = setTimeout(() => {
          try {
            if (
              mediaRecorderRef.current &&
              mediaRecorderRef.current.state === "recording"
            ) {
              mediaRecorderRef.current.stop();
            }
          } catch {
            // ignorar
          }
        }, AUTO_STOP_MS);
      } catch (err) {
        console.error("[ListeningOverlay] getUserMedia error:", err);
        setErrorMsg(
          "No pudimos acceder al micrófono. Revisá los permisos del navegador."
        );
        setPhase("error");
      }
    })();

    return () => {
      cancelled = true;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Animación del waveform — solo mientras grabamos.
  useEffect(() => {
    if (!mounted) return;
    if (phase !== "recording") return;
    const interval = setInterval(() => {
      setBars((prev) => prev.map(() => 0.2 + Math.random() * 0.8));
    }, 100);
    return () => clearInterval(interval);
  }, [phase, mounted]);

  const sendAudio = async (blob: Blob) => {
    try {
      const formData = new FormData();
      formData.append("audio", blob, "care.webm");

      const res = await fetch("/api/care/voice", {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (res.status === 401) {
        setErrorMsg("Tu sesión expiró. Iniciá sesión de nuevo.");
        setPhase("error");
        return;
      }

      const data = (await res.json().catch(() => ({}))) as CareResult & {
        error?: string;
      };

      if (!res.ok) {
        setErrorMsg(
          data?.error ?? `Error ${res.status} al registrar el acto de cuidado.`
        );
        setPhase("error");
        return;
      }

      setResult(data);

      if (data.aprobada === false) {
        setErrorMsg(
          (data.motivo as string) ??
            data.razonamiento ??
            "El Tenzo no aprobó este acto. Probá describirlo con más detalle."
        );
        setPhase("error");
        return;
      }

      setPhase("success");
      onCareRegistered?.(data);

      // Cerrar solo después de mostrar el resultado.
      successTimerRef.current = setTimeout(() => {
        onClose();
      }, SUCCESS_AUTOCLOSE_MS);
    } catch (err) {
      console.error("[ListeningOverlay] sendAudio error:", err);
      setErrorMsg("No pudimos contactar al servidor. Revisá tu conexión.");
      setPhase("error");
    }
  };

  const handleDone = () => {
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    try {
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state === "recording"
      ) {
        mediaRecorderRef.current.stop();
      }
    } catch {
      // ignorar
    }
  };

  const handleRetry = () => {
    setErrorMsg(null);
    setResult(null);
    setPhase("idle");
    // Re-disparamos el efecto cerrando y reabriendo a través de onClose seguido por el padre.
    // Más simple: cerrar y que el usuario vuelva a tocar Voice Register.
    onClose();
  };

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-background/80 backdrop-blur-xl" />

      {/* Close button — siempre disponible */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-4 right-4 z-10 text-muted-foreground hover:text-foreground"
        onClick={onClose}
        aria-label="Cerrar"
      >
        <X className="h-6 w-6" />
      </Button>

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-8 px-6 text-center">
        {/* Visual */}
        {phase === "success" ? (
          <div className="relative h-32 w-32 rounded-full bg-gradient-to-br from-green-500/40 to-emerald-500/40 flex items-center justify-center">
            <Check className="h-14 w-14 text-green-100" strokeWidth={2.5} />
          </div>
        ) : phase === "error" ? (
          <div className="relative h-32 w-32 rounded-full bg-gradient-to-br from-amber-500/30 to-red-500/30 flex items-center justify-center">
            <AlertCircle className="h-14 w-14 text-amber-100" strokeWidth={2} />
          </div>
        ) : phase === "submitting" ? (
          <div className="relative h-32 w-32 rounded-full bg-gradient-to-br from-primary/40 to-accent/40 flex items-center justify-center">
            <Loader2 className="h-14 w-14 text-primary-foreground animate-spin" />
          </div>
        ) : (
          <div className="relative">
            <div className="absolute inset-0 h-32 w-32 animate-ping rounded-full bg-primary/20" />
            <div className="absolute inset-0 h-32 w-32 animate-pulse rounded-full bg-primary/30 blur-xl" />
            <div className="relative h-32 w-32 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center">
              <div className="h-24 w-24 rounded-full bg-background/20 backdrop-blur-sm" />
            </div>
          </div>
        )}

        {/* Waveform — solo mientras grabamos */}
        {phase === "recording" && (
          <div className="flex items-center justify-center gap-1 h-16 w-64">
            {bars.map((height, i) => (
              <div
                key={i}
                className="w-1.5 rounded-full bg-primary/70 transition-all duration-100"
                style={{
                  height: `${height * 100}%`,
                  opacity: 0.4 + height * 0.6,
                }}
              />
            ))}
          </div>
        )}

        {/* Texto de estado */}
        <div className="space-y-2 max-w-sm">
          {phase === "idle" && (
            <h2 className="text-2xl font-light text-foreground">Preparando…</h2>
          )}
          {phase === "recording" && (
            <>
              <h2 className="text-2xl font-light text-foreground">
                Te escucho…
              </h2>
              <p className="text-sm text-muted-foreground">
                Contame qué acto de cuidado realizaste. Tocá{" "}
                <span className="font-medium text-foreground">Done</span> cuando
                termines.
              </p>
            </>
          )}
          {phase === "submitting" && (
            <>
              <h2 className="text-2xl font-light text-foreground">
                Procesando…
              </h2>
              <p className="text-sm text-muted-foreground">
                El Tenzo está evaluando tu contribución.
              </p>
            </>
          )}
          {phase === "success" && (
            <>
              <h2 className="text-2xl font-light text-foreground">
                ¡Registrado!
              </h2>
              {typeof result?.recompensa_hoca === "number" && (
                <p className="text-base text-foreground">
                  +{result.recompensa_hoca}{" "}
                  <span className="text-muted-foreground">HOCA</span>
                </p>
              )}
              {result?.transcripcion && (
                <p className="text-xs text-muted-foreground italic">
                  &ldquo;{result.transcripcion}&rdquo;
                </p>
              )}
            </>
          )}
          {phase === "error" && (
            <>
              <h2 className="text-2xl font-light text-foreground">
                No pudimos registrar este acto
              </h2>
              {errorMsg && (
                <p className="text-sm text-muted-foreground">{errorMsg}</p>
              )}
            </>
          )}
        </div>

        {/* Botones de acción */}
        {phase === "recording" && (
          <Button
            onClick={handleDone}
            size="lg"
            className="rounded-full px-8 h-12 bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Check className="h-4 w-4 mr-2" />
            Done
          </Button>
        )}

        {phase === "error" && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={onClose}
              className="rounded-full px-6"
            >
              Cancelar
            </Button>
            <Button onClick={handleRetry} className="rounded-full px-6">
              Reintentar
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
