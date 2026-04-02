"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Mic, Plus, Users, TrendingUp, Leaf, Globe, LogOut, User, Shield, Eye, Award } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import Image from "next/image";
import { CommunityOrb } from "@/components/hofi/community-orb";
import { ActivityFeed } from "@/components/hofi/activity-feed";
import { HolonView } from "@/components/hofi/holon-view";
import { WorldView } from "@/components/hofi/world-view";
import { ImpactCircles } from "@/components/hofi/impact-circles";
import { PersonalActivity } from "@/components/hofi/personal-activity";
import { CareModal } from "@/components/hofi/care-modal";
import { ListeningOverlay } from "@/components/hofi/listening-overlay";
import { VoiceConnectModal } from "@/components/hofi/voice-connect-modal";
import {
  MOCK_HOLON_STATS,
  MOCK_ACTIVITY_FEED,
  MOCK_SOCIAL_YIELD,
  MOCK_HOLON_LOCATIONS,
  MOCK_IMPACT_CIRCLES,
  MOCK_PERSONAL_TRANSACTIONS,
  type UserRole,
  type UserSession,
  type MetricScope,
} from "@/lib/mock-data";

export default function HoFiDashboard() {
  const [careModalOpen, setCareModalOpen] = useState(false);
  const [listeningMode, setListeningMode] = useState(false);
  const [connectModalOpen, setConnectModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("presence");
  
  // Auth simulation - user session stored in React state
  const [session, setSession] = useState<UserSession | null>(null);
  
  // Derived state from session
  const userRole: UserRole = session?.role ?? "guest";
  const isMember = userRole === "member" || userRole === "guardian";
  const isConnected = session !== null;

  // Try to restore session from server cookie on first load
  useEffect(() => {
    fetch("/api/user/me", { credentials: "include" })
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (!data) return;
        setSession({
          userId: data.userId ?? data.sub ?? `user_${Date.now()}`,
          name: data.name ?? data.email ?? "Member",
          role: data.role ?? "member",
          holonId: data.holonId ?? "holon-piloto",
          balance: data.balance ?? 0,
          avatar: (data.name ?? data.email ?? "M").substring(0, 2).toUpperCase(),
        });
      })
      .catch(() => { /* no cookie — stay as guest */ });
  }, []);

  const handleConnect = (newSession: UserSession) => {
    setSession(newSession);
  };

  const handleDisconnect = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch {
      // ignore network errors on logout
    }
    setSession(null);
  };

  const getRoleIcon = (role: UserRole) => {
    switch (role) {
      case "guardian":
        return Shield;
      case "member":
        return User;
      default:
        return Eye;
    }
  };

  // Map active tab to metric scope
  const getMetricScope = (): MetricScope => {
    switch (activeTab) {
      case "presence":
        return "personal";
      case "holon":
        return "holon";
      case "world":
        return "world";
      default:
        return "personal";
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border/30 bg-background/80 backdrop-blur-lg">
        <div className="container flex h-14 items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <Image 
              src="/hofi-logo.svg" 
              alt="HoFi Logo" 
              width={32} 
              height={32}
              className="rounded-lg"
              loading="eager"
            />
            <span className="font-medium tracking-tight">HoFi</span>
          </div>

          <div className="flex items-center gap-2">
            {isConnected && session ? (
              <>
                {/* Balance pill */}
                <div className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-muted/50 text-xs">
                  <span className="font-medium" suppressHydrationWarning>
                    {session.balance.toLocaleString("en-US")}
                  </span>
                  <span className="text-muted-foreground">HF</span>
                </div>
                
                {/* User avatar with dropdown */}
                <button
                  onClick={handleDisconnect}
                  className="flex items-center gap-2 px-2 py-1 rounded-full hover:bg-muted/50 transition-colors"
                  title="Disconnect"
                >
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="text-xs bg-primary/10 text-primary">
                      {session.avatar}
                    </AvatarFallback>
                  </Avatar>
                  <LogOut className="h-3.5 w-3.5 text-muted-foreground" />
                </button>
              </>
            ) : (
              <Button
                onClick={() => setConnectModalOpen(true)}
                size="sm"
                className="h-8 rounded-full px-4"
              >
                <Mic className="h-3.5 w-3.5 mr-1.5" />
                Connect Voice
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container px-4 py-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          {/* Tab Navigation */}
          <TabsList className="grid w-full grid-cols-3 h-11 bg-muted/30 rounded-xl p-1">
            <TabsTrigger
              value="presence"
              className="rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm"
            >
              <Leaf className="h-4 w-4 mr-2" />
              Presence
            </TabsTrigger>
            <TabsTrigger
              value="holon"
              className="rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm"
            >
              <Users className="h-4 w-4 mr-2" />
              Holon
            </TabsTrigger>
            <TabsTrigger
              value="world"
              className="rounded-lg data-[state=active]:bg-card data-[state=active]:shadow-sm"
            >
              <Globe className="h-4 w-4 mr-2" />
              World
            </TabsTrigger>
          </TabsList>

          {/* Presence Dashboard */}
          <TabsContent value="presence" className="space-y-6 mt-0">
            {/* User Header - shown when connected */}
            {isConnected && session && (
              <Card className="p-4 border-border/30 bg-card/50">
                <div className="flex items-center gap-4">
                  <Avatar className="h-14 w-14">
                    <AvatarFallback className="text-lg bg-primary/10 text-primary">
                      {session.avatar}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <h2 className="text-lg font-medium">{session.name}</h2>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-sm text-muted-foreground capitalize">
                        {session.role}
                      </span>
                      <div className="flex items-center gap-1 text-sm">
                        <span className="font-semibold text-primary" suppressHydrationWarning>
                          {session.balance.toLocaleString("en-US")}
                        </span>
                        <span className="text-muted-foreground">HOCA</span>
                      </div>
                    </div>
                  </div>
                  {/* SBT Badge placeholder */}
                  <div className="flex flex-col items-center gap-1">
                    <div className="h-10 w-10 rounded-full bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center">
                      <Award className="h-5 w-5 text-primary" />
                    </div>
                    <span className="text-[10px] text-muted-foreground">SBT</span>
                  </div>
                </div>
              </Card>
            )}

            {/* Impact Circles - Replace CommunityOrb */}
            {isConnected && (
              <section className="py-4">
                <ImpactCircles 
                  data={MOCK_IMPACT_CIRCLES} 
                  scope="personal" 
                />
              </section>
            )}

            {/* Community Stats */}
            {!isConnected && (
              <section className="flex flex-col items-center py-6">
                <CommunityOrb health={MOCK_HOLON_STATS.health} />
                
                {/* Stats beneath orb */}
                <div className="flex items-center gap-6 mt-6 text-center">
                  <div>
                    <p className="text-2xl font-light">{MOCK_HOLON_STATS.totalMembers}</p>
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">
                      Members
                    </p>
                  </div>
                  <div className="h-8 w-px bg-border" />
                  <div>
                    <p className="text-2xl font-light">{MOCK_HOLON_STATS.activeCaregivers}</p>
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">
                      Active
                    </p>
                  </div>
                  <div className="h-8 w-px bg-border" />
                  <div className="flex items-center gap-1">
                    <TrendingUp className="h-4 w-4 text-primary" />
                    <p className="text-2xl font-light">{MOCK_HOLON_STATS.weeklyGrowth}%</p>
                  </div>
                </div>
              </section>
            )}

            {/* Voice-first Register Care Button */}
            <section className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Button
                  onClick={() => setListeningMode(true)}
                  className="h-14 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
                >
                  <Mic className="h-5 w-5 mr-2" />
                  Voice Register
                </Button>
                <Button
                  onClick={() => setCareModalOpen(true)}
                  variant="outline"
                  className="h-14 rounded-xl border-border/50 hover:bg-muted/50"
                >
                  <Plus className="h-5 w-5 mr-2" />
                  Manual Entry
                </Button>
              </div>
            </section>

            {/* Personal Activity / Transactions */}
            {isConnected && (
              <section>
                <PersonalActivity transactions={MOCK_PERSONAL_TRANSACTIONS} />
              </section>
            )}

            {/* Activity Feed - shown to guests */}
            {!isConnected && (
              <section>
                <ActivityFeed 
                  activities={MOCK_ACTIVITY_FEED} 
                  isMember={isMember}
                />
              </section>
            )}
          </TabsContent>

          {/* Holon View */}
          <TabsContent value="holon" className="space-y-6 mt-0">
            {/* Impact Circles - holon scope */}
            {isConnected && (
              <section className="py-2">
                <ImpactCircles 
                  data={MOCK_IMPACT_CIRCLES} 
                  scope="holon" 
                />
              </section>
            )}
            
            <HolonView
              activities={MOCK_ACTIVITY_FEED}
              socialYield={MOCK_SOCIAL_YIELD}
              userRole={userRole}
            />
          </TabsContent>

          {/* World View */}
          <TabsContent value="world" className="mt-0 space-y-4">
            {/* Impact Circles - world scope - compact mode */}
            {isConnected && (
              <section>
                <ImpactCircles 
                  data={MOCK_IMPACT_CIRCLES} 
                  scope="world"
                  compact={true}
                />
              </section>
            )}
            
            <WorldView holons={MOCK_HOLON_LOCATIONS} />
          </TabsContent>
        </Tabs>
      </main>

      {/* Care Registration Modal */}
      <CareModal open={careModalOpen} onOpenChange={setCareModalOpen} />

      {/* Listening Mode Overlay */}
      <ListeningOverlay
        active={listeningMode}
        onClose={() => setListeningMode(false)}
      />

      {/* Voice Connect Modal */}
      <VoiceConnectModal
        open={connectModalOpen}
        onOpenChange={setConnectModalOpen}
        onConnect={handleConnect}
      />
    </div>
  );
}
