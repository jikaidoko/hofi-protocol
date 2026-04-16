"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { X, Users, Coins, Sparkles, ZoomOut, AlertCircle } from "lucide-react";
import type { HolonLocation, CareCategory } from "@/lib/mock-data";
import { ACTIVITY_CATEGORIES } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

interface WorldViewProps {
  holons: HolonLocation[];
}

const WORLD_VIEW = { zoom: 2, center: [0, 20] as [number, number] };
const CLUSTER_ZOOM = 10;
const MAX_ZOOM = 13;

export function WorldView({ holons }: WorldViewProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const [selectedHolon, setSelectedHolon] = useState<HolonLocation | null>(null);
  const [isZoomedIn, setIsZoomedIn] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const animationId = useRef<number | null>(null);
  const userInteracting = useRef(false);

  // Convert holons to GeoJSON
  const geojsonData = {
    type: "FeatureCollection" as const,
    features: holons.map((holon) => ({
      type: "Feature" as const,
      properties: {
        id: holon.id,
        name: holon.name,
        city: holon.city,
        activeMembers: holon.activeMembers,
        totalHocaDistributed: holon.totalHocaDistributed,
        topCategory: holon.topCategory,
      },
      geometry: {
        type: "Point" as const,
        coordinates: holon.coordinates,
      },
    })),
  };

  const getCategoryLabel = (category: CareCategory) => {
    return ACTIVITY_CATEGORIES[category]?.label || category;
  };

  const handleZoomOut = useCallback(() => {
    if (map.current) {
      map.current.flyTo({
        center: WORLD_VIEW.center,
        zoom: WORLD_VIEW.zoom,
        duration: 1500,
        essential: true,
      });
      setSelectedHolon(null);
      setIsZoomedIn(false);
    }
  }, []);

  useEffect(() => {
    if (!mapContainer.current) return;

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) {
      setMapError("Mapbox token not configured. Add NEXT_PUBLIC_MAPBOX_TOKEN to environment variables.");
      return;
    }

    mapboxgl.accessToken = token;

    const mapInstance = new mapboxgl.Map({
      container: mapContainer.current,
      style: "mapbox://styles/mapbox/dark-v11",
      center: [20, 5], // Start centered on Africa
      zoom: WORLD_VIEW.zoom,
      projection: "globe", // Use globe projection
      attributionControl: false,
    });

    map.current = mapInstance;

    // Add zoom controls
    mapInstance.addControl(new mapboxgl.NavigationControl(), "top-right");

    // Add atmosphere effect and start rotation
    mapInstance.on("style.load", () => {
      mapInstance.setFog({
        color: "rgb(10, 10, 20)",
        "high-color": "rgb(30, 40, 80)",
        "horizon-blend": 0.02,
        "space-color": "rgb(5, 5, 15)",
        "star-intensity": 0.6,
      });

      // Start auto-rotation
      const rotate = () => {
        if (!userInteracting.current && map.current) {
          const center = map.current.getCenter();
          center.lng -= 0.05; // Slow westward rotation
          map.current.setCenter(center);
          animationId.current = requestAnimationFrame(rotate);
        }
      };
      animationId.current = requestAnimationFrame(rotate);
    });

    mapInstance.on("load", () => {
      setMapLoaded(true);

      // Add source with clustering enabled
      mapInstance.addSource("holons", {
        type: "geojson",
        data: geojsonData,
        cluster: true,
        clusterMaxZoom: 10,
        clusterRadius: 100, // 100px radius for clustering
      });

      // Cluster circles layer
      mapInstance.addLayer({
        id: "clusters",
        type: "circle",
        source: "holons",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#8ba981",
          "circle-radius": 18,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#c9a961",
        },
      });

      // Cluster count labels
      mapInstance.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "holons",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["DIN Offc Pro Medium", "Arial Unicode MS Bold"],
          "text-size": 12,
        },
        paint: {
          "text-color": "#ffffff",
        },
      });

      // Individual holon markers (unclustered points)
      mapInstance.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "holons",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": "#8ba981",
          "circle-radius": 6,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#c9a961",
        },
      });

      // Outer glow for unclustered points
      mapInstance.addLayer({
        id: "unclustered-point-glow",
        type: "circle",
        source: "holons",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": "rgba(139, 169, 129, 0.3)",
          "circle-radius": 12,
        },
      }, "unclustered-point");

      // Click handler for clusters - fly to expand
      mapInstance.on("click", "clusters", (e) => {
        const features = mapInstance.queryRenderedFeatures(e.point, {
          layers: ["clusters"],
        });

        if (!features.length) return;

        const clusterId = features[0].properties?.cluster_id;
        const source = mapInstance.getSource("holons") as mapboxgl.GeoJSONSource;

        // Get the leaves (individual points) in this cluster
        source.getClusterLeaves(clusterId, 100, 0, (err, leaves) => {
          if (err || !leaves) return;

          source.getClusterExpansionZoom(clusterId, (err, zoom) => {
            if (err) return;

            const geometry = features[0].geometry;
            if (geometry.type === "Point") {
              const coordinates = geometry.coordinates as [number, number];
              
              // Zoom level capped between CLUSTER_ZOOM and MAX_ZOOM
              const targetZoom = Math.min(Math.max(zoom || CLUSTER_ZOOM, CLUSTER_ZOOM), MAX_ZOOM);
              
              mapInstance.flyTo({
                center: coordinates,
                zoom: targetZoom,
                duration: 1500,
                essential: true,
              });
              
              // After flyTo completes, check if holons are still overlapping
              // and use fitBounds if needed to ensure all are visible
              mapInstance.once("moveend", () => {
                if (leaves.length > 1) {
                  const bounds = new mapboxgl.LngLatBounds();
                  leaves.forEach((leaf) => {
                    if (leaf.geometry.type === "Point") {
                      bounds.extend(leaf.geometry.coordinates as [number, number]);
                    }
                  });
                  
                  // Only fitBounds if the bounds are valid and markers might overlap
                  if (!bounds.isEmpty()) {
                    mapInstance.fitBounds(bounds, {
                      padding: 80,
                      maxZoom: MAX_ZOOM,
                      duration: 800,
                    });
                  }
                }
              });
              
              setIsZoomedIn(true);
              setSelectedHolon(null);
            }
          });
        });
      });

      // Click handler for individual markers
      mapInstance.on("click", "unclustered-point", (e) => {
        if (!e.features || !e.features[0]) return;

        const properties = e.features[0].properties;
        if (!properties) return;

        const holon = holons.find((h) => h.id === properties.id);
        if (holon) {
          setSelectedHolon(holon);
        }
      });

      // Change cursor on hover
      mapInstance.on("mouseenter", "clusters", () => {
        mapInstance.getCanvas().style.cursor = "pointer";
      });
      mapInstance.on("mouseleave", "clusters", () => {
        mapInstance.getCanvas().style.cursor = "";
      });
      mapInstance.on("mouseenter", "unclustered-point", () => {
        mapInstance.getCanvas().style.cursor = "pointer";
      });
      mapInstance.on("mouseleave", "unclustered-point", () => {
        mapInstance.getCanvas().style.cursor = "";
      });

      // Track zoom level for UI
      mapInstance.on("zoomend", () => {
        const currentZoom = mapInstance.getZoom();
        setIsZoomedIn(currentZoom > 4);
      });

      // Stop rotation on user interaction
      const stopRotation = () => {
        userInteracting.current = true;
        if (animationId.current) {
          cancelAnimationFrame(animationId.current);
          animationId.current = null;
        }
      };

      mapInstance.on("mousedown", stopRotation);
      mapInstance.on("touchstart", stopRotation);
      mapInstance.on("wheel", stopRotation);
    });

    mapInstance.on("error", (e) => {
      console.error("Mapbox error:", e);
      setMapError("Failed to load map. Please check your Mapbox token.");
    });

    return () => {
      if (animationId.current) {
        cancelAnimationFrame(animationId.current);
      }
      mapInstance.remove();
    };
  }, [holons]);

  // Update source when holons change
  useEffect(() => {
    if (map.current && mapLoaded) {
      const source = map.current.getSource("holons") as mapboxgl.GeoJSONSource;
      if (source) {
        source.setData(geojsonData);
      }
    }
  }, [holons, mapLoaded]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="text-center">
        <h2 className="text-2xl font-light tracking-tight">The World</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Holones across the globe
        </p>
      </div>

      {/* Map Container */}
      <Card className="relative overflow-hidden rounded-2xl border-border/30 bg-[#1a1f2e]">
        <div className="aspect-[16/10] w-full">
          {mapError ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <AlertCircle className="h-12 w-12 text-destructive mb-4" />
              <p className="text-sm text-muted-foreground">{mapError}</p>
            </div>
          ) : (
            <div ref={mapContainer} className="w-full h-full" />
          )}
        </div>

        {/* Zoom Out Button - top left */}
        {isZoomedIn && !mapError && (
          <div className="absolute top-4 left-4">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleZoomOut}
              className="bg-black/50 hover:bg-black/70 text-white border-none backdrop-blur-sm"
            >
              <ZoomOut className="h-4 w-4 mr-2" />
              World View
            </Button>
          </div>
        )}

        {/* Legend - top right, offset below navigation controls */}
        {!mapError && (
          <div className="absolute top-20 right-4 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/40 backdrop-blur-sm">
            <div className="h-2 w-2 rounded-full bg-[#8ba981]" />
            <span className="text-xs text-white/70">
              {holons.length} Holones
            </span>
          </div>
        )}

        {/* Selected Holon Card - bottom */}
        {selectedHolon && (
          <div className="absolute bottom-0 left-0 right-0 p-4 animate-in slide-in-from-bottom-4 duration-300">
            <Card className="p-4 bg-card/95 backdrop-blur-lg border-border/50 shadow-xl">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-medium text-lg">{selectedHolon.name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {selectedHolon.city}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedHolon(null)}
                  className="p-1 rounded-full hover:bg-muted/50 transition-colors"
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>

              <div className="grid grid-cols-3 gap-4 mt-4">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <Users className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{selectedHolon.activeMembers}</p>
                    <p className="text-xs text-muted-foreground">Active</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-amber-500/10 flex items-center justify-center">
                    <Coins className="h-4 w-4 text-amber-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium" suppressHydrationWarning>
                      {selectedHolon.totalHocaDistributed.toLocaleString("en-US")}
                    </p>
                    <p className="text-xs text-muted-foreground">HOCA</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <div className={cn(
                    "h-8 w-8 rounded-full flex items-center justify-center",
                    ACTIVITY_CATEGORIES[selectedHolon.topCategory]?.bgColor + "/20"
                  )}>
                    <Sparkles className={cn(
                      "h-4 w-4",
                      ACTIVITY_CATEGORIES[selectedHolon.topCategory]?.color
                    )} />
                  </div>
                  <div>
                    <p className="text-sm font-medium capitalize">
                      {getCategoryLabel(selectedHolon.topCategory)}
                    </p>
                    <p className="text-xs text-muted-foreground">Top</p>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        )}
      </Card>
    </div>
  );
}
