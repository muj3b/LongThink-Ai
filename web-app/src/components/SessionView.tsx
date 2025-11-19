import { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { Terminal, Activity } from 'lucide-react';
import { BrainVisualizer } from './BrainVisualizer';
import { cn } from '../lib/utils';



export function SessionView() {
    const [sessionId, setSessionId] = useState<string>('');
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const { events, isConnected } = useWebSocket(activeSessionId);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [events]);

    const handleConnect = () => {
        if (sessionId) setActiveSessionId(sessionId);
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center space-x-4">
                <input
                    type="text"
                    placeholder="Enter Session ID"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 max-w-sm"
                    value={sessionId}
                    onChange={(e) => setSessionId(e.target.value)}
                />
                <button
                    onClick={handleConnect}
                    className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
                >
                    Connect
                </button>
                <div className={`flex items-center space-x-2 ${isConnected ? 'text-green-500' : 'text-red-500'}`}>
                    <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                    <span className="text-sm font-medium">{isConnected ? 'Live' : 'Disconnected'}</span>
                </div>
            </div>

            <div className="grid gap-6 md:grid-cols-3">
                <div className="md:col-span-2 space-y-6">
                    <div className="rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden">
                        <div className="p-6 flex flex-col space-y-3">
                            <h3 className="font-semibold leading-none tracking-tight flex items-center gap-2">
                                <Terminal className="h-4 w-4 text-primary" />
                                Live Reasoning Stream
                            </h3>
                            <div className="h-[500px] w-full rounded-md border bg-black/90 p-4 overflow-y-auto font-mono text-xs space-y-2 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
                                {events.length === 0 ? (
                                    <div className="text-muted-foreground flex flex-col items-center justify-center h-full">
                                        <Activity className="h-8 w-8 mb-2 opacity-50 animate-pulse" />
                                        <span>Waiting for neural activity...</span>
                                    </div>
                                ) : (
                                    events.map((event, i) => (
                                        <LogEntry key={i} event={event} />
                                    ))
                                )}
                                <div ref={bottomRef} />
                            </div>
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="rounded-xl border bg-card text-card-foreground shadow-sm">
                        <div className="p-6 flex flex-col space-y-3">
                            <h3 className="font-semibold leading-none tracking-tight flex items-center gap-2">
                                <Activity className="h-4 w-4 text-accent" />
                                Neural Activity
                            </h3>
                            <BrainVisualizer isActive={isConnected && events.length > 0} />
                            <div className="text-xs text-muted-foreground text-center">
                                {isConnected ? 'Network Active' : 'Network Idle'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function LogEntry({ event }: { event: any }) {
    // Try to parse if it's a string, otherwise use as is
    let content = event;
    if (typeof event === 'object' && event.data) {
        content = event.data;
    }

    const isError = JSON.stringify(content).toLowerCase().includes('error');
    const isSuccess = JSON.stringify(content).toLowerCase().includes('success') || JSON.stringify(content).toLowerCase().includes('completed');

    return (
        <div className={cn(
            "p-2 rounded border-l-2 pl-3 break-words transition-all duration-300 animate-in fade-in slide-in-from-left-2",
            isError ? "border-red-500 bg-red-950/10 text-red-200" :
                isSuccess ? "border-green-500 bg-green-950/10 text-green-200" :
                    "border-blue-500/30 hover:bg-white/5"
        )}>
            <span className="text-slate-500 mr-2">[{new Date().toLocaleTimeString()}]</span>
            <span className="font-mono">{typeof content === 'string' ? content : JSON.stringify(content, null, 2)}</span>
        </div>
    )
}
