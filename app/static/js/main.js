function handleJoin(role) {

    const session_id = document.getElementById('session-id').value.trim();
    const user_name = document.getElementById('user-name').value.trim();

    if ("" === session_id || "" === user_name || "" === role) {
        alert('Please Insert the valid session id or user_name');
        return;
    }

    window.location.href = `/session/${encodeURIComponent(session_id)}/?role=${encodeURIComponent(role)}&name=${encodeURIComponent(user_name)}`;
}