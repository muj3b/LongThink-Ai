import { useState, useEffect } from 'react';
import { Activity, Clock, Cpu, Zap, PlayCircle, Plus } from 'lucide-react';
import { SessionView } from './SessionView';
import { NewSessionModal } from './NewSessionModal';

interface Session {
    session_id: string;
    status: string;
    question: string;
    rounds: number;
    elapsed_seconds: number;
}

export function Dashboard() {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [loading, setLoading] = useState(true);
    const [isModalOpen, setIsModalOpen] = useState(false);

    const fetchSessions = () => {
        setLoading(true);
        fetch('http://localhost:8000/sessions?limit=5')
            .then(res => res.json())
            .then(data => {
                setSessions(data);
                setLoading(false);
            })
            .catch(err => {
                console.error('Failed to fetch sessions:', err);
                setLoading(false);
            });
    };

    useEffect(() => {
        fetchSessions();
    }, []);

    const activeSessions = sessions.filter(s => !s.status || s.status === 'running').length;
    const totalTime = sessions.reduce((acc, s) => acc + (s.elapsed_seconds || 0), 0);
    const avgRounds = sessions.length ? Math.round(sessions.reduce((acc, s) => acc + (s.rounds || 0), 0) / sessions.length) : 0;

    return (
        <div className="space-y-8">
            <div className="flex items-center justify-between space-y-2">
                <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
                <div className="flex items-center space-x-2">
                    <button
                        onClick={() => setIsModalOpen(true)}
                        className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 gap-2"
                    >
                        <Plus className="h-4 w-4" />
                        New Session
                    </button>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card title="Active Sessions" value={activeSessions.toString()} icon={Activity} description="Currently running" />
                <Card title="Total Time" value={`${Math.round(totalTime / 60)}m`} icon={Clock} description="Reasoning duration" />
                <Card title="Avg. Rounds" value={avgRounds.toString()} icon={Zap} description="Depth of thought" />
                <Card title="Total Sessions" value={sessions.length.toString()} icon={Cpu} description="All time runs" />
            </div>

            {/* Recent Activity */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <div className="col-span-4 rounded-xl border bg-card text-card-foreground shadow-sm">
                    <div className="p-6 flex flex-col space-y-3">
                        <h3 className="font-semibold leading-none tracking-tight">Recent Sessions</h3>
                        <p className="text-sm text-muted-foreground">
                            Latest reasoning traces and decisions.
                        </p>
                        <div className="space-y-4">
                            {loading ? (
                                <div className="text-center p-4 text-muted-foreground">Loading sessions...</div>
                            ) : sessions.length === 0 ? (
                                <div className="text-center p-4 text-muted-foreground">No sessions found. Start one!</div>
                            ) : (
                                sessions.map((session) => (
                                    <div key={session.session_id} className="flex items-center justify-between p-3 rounded-lg border bg-muted/50 hover:bg-muted transition-colors">
                                        <div className="flex items-center gap-3 overflow-hidden">
                                            <div className={`h-2 w-2 rounded-full ${!session.status || session.status === 'running' ? 'bg-green-500 animate-pulse' : 'bg-slate-500'}`} />
                                            <div className="flex flex-col min-w-0">
                                                <span className="font-medium truncate text-sm">{session.question || 'Untitled Session'}</span>
                                                <span className="text-xs text-muted-foreground font-mono">{session.session_id}</span>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-4 text-sm text-muted-foreground whitespace-nowrap">
                                            <span>{session.rounds || 0} rounds</span>
                                            <span>{session.elapsed_seconds || 0}s</span>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
                <div className="col-span-3 rounded-xl border bg-card text-card-foreground shadow-sm">
                    <div className="p-6 flex flex-col space-y-3">
                        <h3 className="font-semibold leading-none tracking-tight">Quick Actions</h3>
                        <p className="text-sm text-muted-foreground">
                            Launch common reasoning tasks.
                        </p>
                        <div className="grid gap-2">
                            <button className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30 hover:bg-accent hover:text-accent-foreground transition-colors text-left">
                                <PlayCircle className="h-5 w-5 text-primary" />
                                <div>
                                    <div className="font-medium text-sm">Quick Logic Check</div>
                                    <div className="text-xs text-muted-foreground">Fast verification (1-2 mins)</div>
                                </div>
                            </button>
                            <button className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30 hover:bg-accent hover:text-accent-foreground transition-colors text-left">
                                <PlayCircle className="h-5 w-5 text-purple-400" />
                                <div>
                                    <div className="font-medium text-sm">Deep Research</div>
                                    <div className="text-xs text-muted-foreground">Extended thinking (30+ mins)</div>
                                </div>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <SessionView />

            <NewSessionModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onCreated={fetchSessions}
            />
        </div>
    );
}

function Card({ title, value, icon: Icon, description }: { title: string, value: string, icon: any, description: string }) {
    return (
        <div className="rounded-xl border bg-card text-card-foreground shadow-sm">
            <div className="p-6 flex flex-row items-center justify-between space-y-0 pb-2">
                <h3 className="tracking-tight text-sm font-medium">{title}</h3>
                <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="p-6 pt-0">
                <div className="text-2xl font-bold">{value}</div>
                <p className="text-xs text-muted-foreground">{description}</p>
            </div>
        </div>
    );
}
