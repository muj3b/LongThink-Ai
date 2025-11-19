import { useEffect, useRef, useState } from 'react';

export function useWebSocket(sessionId: string | null) {
    const [events, setEvents] = useState<any[]>([]);
    const [isConnected, setIsConnected] = useState(false);
    const ws = useRef<WebSocket | null>(null);

    useEffect(() => {
        if (!sessionId) return;

        const socket = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);

        socket.onopen = () => {
            setIsConnected(true);
            console.log('Connected to WebSocket');
        };

        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'init') {
                setEvents(data.events);
            } else if (data.type === 'event') {
                setEvents((prev) => [...prev, data.data]);
            }
        };

        socket.onclose = () => {
            setIsConnected(false);
            console.log('Disconnected from WebSocket');
        };

        ws.current = socket;

        return () => {
            socket.close();
        };
    }, [sessionId]);

    return { events, isConnected };
}
