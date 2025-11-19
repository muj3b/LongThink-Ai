import React, { useEffect, useState } from 'react';
import { Brain } from 'lucide-react';


interface LayoutProps {
    children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
    const [isOnline, setIsOnline] = useState(false);

    useEffect(() => {
        const checkHealth = () => {
            fetch('http://localhost:8000/health')
                .then(res => res.ok ? setIsOnline(true) : setIsOnline(false))
                .catch(() => setIsOnline(false));
        };

        checkHealth();
        const interval = setInterval(checkHealth, 30000); // Check every 30s
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="min-h-screen bg-background text-foreground font-sans selection:bg-accent selection:text-accent-foreground">
            <div className="fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black"></div>

            {/* Header */}
            <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="container flex h-14 max-w-screen-2xl items-center">
                    <div className="mr-4 flex items-center space-x-2">
                        <Brain className="h-6 w-6 text-chart-1" />
                        <span className="hidden font-bold sm:inline-block">LongThink AI</span>
                    </div>
                    <nav className="flex items-center space-x-6 text-sm font-medium">
                        <a href="#" className="transition-colors hover:text-foreground/80 text-foreground">Dashboard</a>
                        <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">Sessions</a>
                        <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">Settings</a>
                    </nav>
                    <div className="ml-auto flex items-center space-x-4">
                        <div className="flex items-center space-x-1">
                            <div className={`h-2 w-2 rounded-full ${isOnline ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
                            <span className="text-xs text-muted-foreground">{isOnline ? 'System Online' : 'Backend Offline'}</span>
                        </div>
                    </div>
                </div>
            </header>

            <main className="container max-w-screen-2xl py-6">
                {children}
            </main>
        </div>
    );
}
