import React, { useState } from 'react';
import { X } from 'lucide-react';

interface NewSessionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onCreated: () => void;
}

export function NewSessionModal({ isOpen, onClose, onCreated }: NewSessionModalProps) {
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await fetch('http://localhost:8000/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt }),
            });
            if (res.ok) {
                setPrompt('');
                onCreated();
                onClose();
            }
        } catch (error) {
            console.error('Failed to create session:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-lg animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold">Start New Session</h2>
                    <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
                        <X className="h-4 w-4" />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                            Prompt / Question
                        </label>
                        <textarea
                            className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            placeholder="What should the AI think about?"
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            required
                        />
                    </div>
                    <div className="flex justify-end space-x-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading}
                            className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
                        >
                            {loading ? 'Launching...' : 'Start Thinking'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
