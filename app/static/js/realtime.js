/**
 * WebSocket Realtime Client with reconnection
 */

let socket = null;
let currentSessionId = null;

function initSocket() {
    if (socket && socket.connected) return socket;

    socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: Infinity,
        transports: ['websocket', 'polling'],
    });

    socket.on('connect', () => {
        console.log('[WS] Connected');
        socket.emit('join_room', { room: 'dashboard' });
        // Re-join session if we were in one
        if (currentSessionId) {
            socket.emit('join_session', { session_id: currentSessionId });
        }
        updateConnectionStatus(true);
    });

    socket.on('disconnect', (reason) => {
        console.log('[WS] Disconnected:', reason);
        updateConnectionStatus(false);
    });

    socket.on('connect_error', (err) => {
        console.warn('[WS] Connection error:', err.message);
        updateConnectionStatus(false);
    });

    socket.on('reconnect', (attemptNumber) => {
        console.log('[WS] Reconnected after', attemptNumber, 'attempts');
        updateConnectionStatus(true);
    });

    // Listen for live updates
    socket.on('student_marked', (data) => {
        if (typeof onStudentMarked === 'function') onStudentMarked(data);
    });

    socket.on('stats_update', (stats) => {
        if (typeof onStatsUpdate === 'function') onStatsUpdate(stats);
    });

    return socket;
}

function updateConnectionStatus(connected) {
    const el = document.getElementById('ws-status');
    if (el) {
        el.className = connected ? 'ws-connected' : 'ws-disconnected';
        el.textContent = connected ? 'Connected' : 'Reconnecting...';
        el.title = connected ? 'WebSocket connected' : 'WebSocket disconnected — reconnecting';
    }
}

function joinSession(sessionId) {
    currentSessionId = sessionId;
    if (!socket) initSocket();
    if (socket.connected) {
        socket.emit('join_session', { session_id: sessionId });
    }
}

function leaveSession(sessionId) {
    currentSessionId = null;
    if (socket) socket.emit('leave_session', { session_id: sessionId });
}

// Auto-init on page load
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname !== '/login') {
        initSocket();
    }
});
