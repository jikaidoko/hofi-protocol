"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Leaf, UtensilsCrossed, BookOpen, Heart, Hammer, HandHeart, Bot, Send, PawPrint, Mountain, Package } from "lucide-react";
import { cn } from "@/lib/utils";

interface CareModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const categories = [
  { value: "gardening", label: "Gardening", icon: Leaf },
  { value: "cooking", label: "Cooking", icon: UtensilsCrossed },
  { value: "teaching", label: "Teaching", icon: BookOpen },
  { value: "healing", label: "Healing", icon: Heart },
  { value: "building", label: "Building", icon: Hammer },
  { value: "caring", label: "Caring", icon: HandHeart },
  { value: "animals", label: "Animals", icon: PawPrint },
  { value: "land", label: "Land", icon: Mountain },
  { value: "resources", label: "Resources", icon: Package },
];

interface TenzoResult {
  razonamiento: string;
  recompensa_hoca: number;
}

export function CareModal({ open, onOpenChange }: CareModalProps) {
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [duration, setDuration] = useState("");
  const [location, setLocation] = useState("");
  const [tenzoResult, setTenzoResult] = useState<TenzoResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      // Usamos la API route interna en vez de llamar al Tenzo directamente.
      // Esto mantiene la API key fuera del browser y centraliza el logging.
      const response = await fetch("/api/care/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          descripcion: description,
          categoria: category,
          duracion_horas: parseFloat(duration) || 1,
          holon_id: "familia-valdez",
          ...(location ? { ubicacion: location } : {}),
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData?.error ?? `Error ${response.status}`);
      }

      const data = await response.json();
      setTenzoResult({
        razonamiento: data.razonamiento,
        recompensa_hoca: data.recompensa_hoca,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to register care");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setDescription("");
    setCategory("");
    setDuration("");
    setLocation("");
    setTenzoResult(null);
    setError(null);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md bg-card border-border/50">
        <DialogHeader>
          <DialogTitle className="text-xl font-light">Register Care</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Share your contribution to the community
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-4">
          {/* Category Selection */}
          <div className="space-y-2">
            <Label className="text-sm text-muted-foreground">
              Type of Care
            </Label>
            <div className="grid grid-cols-3 gap-2">
              {categories.map((cat) => {
                const Icon = cat.icon;
                return (
                  <button
                    key={cat.value}
                    type="button"
                    onClick={() => setCategory(cat.value)}
                    className={cn(
                      "flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all",
                      category === cat.value
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border/50 hover:border-border hover:bg-muted/50"
                    )}
                  >
                    <Icon className="h-5 w-5" />
                    <span className="text-xs">{cat.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="description" className="text-sm text-muted-foreground">
              What did you do?
            </Label>
            <Textarea
              id="description"
              placeholder="Describe your care activity..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-h-24 resize-none bg-muted/30 border-border/50 focus:border-primary"
            />
          </div>

          {/* Duration */}
          <div className="space-y-2">
            <Label htmlFor="duration" className="text-sm text-muted-foreground">
              Duration (hours)
            </Label>
            <Input
              id="duration"
              type="number"
              min="0.5"
              step="0.5"
              placeholder="e.g., 1.5"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              className="bg-muted/30 border-border/50 focus:border-primary"
            />
          </div>

          {/* Location */}
          <div className="space-y-2">
            <Label htmlFor="location" className="text-sm text-muted-foreground">
              Location (optional)
            </Label>
            <Input
              id="location"
              placeholder="Where did this happen?"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="bg-muted/30 border-border/50 focus:border-primary"
            />
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/20">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          {/* Tenzo Agent Response */}
          {tenzoResult && (
            <div className="flex gap-3 p-4 rounded-xl bg-primary/5 border border-primary/20">
              <div className="flex-shrink-0 h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                <Bot className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1">
                <p className="text-xs font-medium text-primary mb-1">Tenzo Agent</p>
                <p className="text-sm text-foreground/80 leading-relaxed mb-2">
                  {tenzoResult.razonamiento}
                </p>
                <div className="flex items-center gap-2 text-sm font-medium text-primary">
                  <Leaf className="h-4 w-4" />
                  <span>{tenzoResult.recompensa_hoca} HOCA earned</span>
                </div>
              </div>
            </div>
          )}

          {/* Submit Button */}
          <Button
            onClick={tenzoResult ? handleClose : handleSubmit}
            disabled={isSubmitting || (!tenzoResult && (!category || !description || !duration))}
            className="w-full h-12 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                Registering...
              </span>
            ) : tenzoResult ? (
              "Done"
            ) : (
              <span className="flex items-center gap-2">
                <Send className="h-4 w-4" />
                Register Care
              </span>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
