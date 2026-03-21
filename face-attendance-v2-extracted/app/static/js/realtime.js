/**
 * WebSocket Realtime Client
 */

let socket = null;

function initSocket() {
    if (socket) return socket;

    socket = io({
        auth: { token: getToken() },
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 10,
    });

    socket.on('connect', () => {
        console.log('[WS] Connected');
        socket.emit('join_room', { room: 'dashboard' });
    });

    socket.on('disconnect', () => {
        console.log('[WS] Disconnected');
    });

    socket.on('connect_error', (err) => {
        console.warn('[WS] Connection error:', err.message);
    });

    return socket;
}

function joinSession(sessionId) {
    if (!socket) initSocket();
    socket.emit('join_session', { session_id: sessionId });
}

function leaveSession(sessionId) {
    if (socket) socket.emit('leave_session', { session_id: sessionId });
}

// Auto-init on page load
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname !== '/login') {
        initSocket();
    }
});
