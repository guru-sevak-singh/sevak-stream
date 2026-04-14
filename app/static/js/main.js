let socket;

function InitilizeWebSocket(role, session_id, user_name) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const socket_url = `${protocol}//${host}/session/ws/${encodeURIComponent(session_id)}/?role=${encodeURIComponent(role)}&name=${encodeURIComponent(user_name)}`
    console.log(socket_url);
    socket = new WebSocket(socket_url);

    socket.onopen = (event) => {
        console.log('Socket was connected...');
    }
    socket.onmessage = (event) => {
        console.log('event => ', event);
    }
    socket.onclose = (event) => {
        console.log('socket is going to close....');
        console.error('event => ', event);
    }
}


function handleJoin(role) {

    const session_id = document.getElementById('session-id').value.trim();
    const user_name = document.getElementById('user-name').value.trim();

    console.log('session id =>', session_id, '\nuser name => ', user_name);

    if ("" === session_id || "" === user_name || "" === role) {
        alert('Please Insert the valid session id or user_name');
        return;
    }

    InitilizeWebSocket(role,  session_id, user_name);
}