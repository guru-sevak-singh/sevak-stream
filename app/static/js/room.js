// ─── state ───────────────────────────────────────────────────────────────────
let socket        = null
let peerConnection = null
let stream        = null

// ─── read from URL ────────────────────────────────────────────────────────────
// room URL looks like: /session/abc123?role=teacher&name=Guru
const urlParams  = new URLSearchParams(window.location.search)
const role       = urlParams.get('role')
const user_name  = urlParams.get('name')
const session_id = window.location.pathname.split('/').filter(Boolean).pop()
// filter(Boolean) removes empty strings from split
// .pop() gets the last part — which is session_id

// ─── ICE servers ─────────────────────────────────────────────────────────────
const ICE_SERVERS = {
    iceServers: [
        { urls: "stun:stun.relay.metered.ca:80" },
        {
            urls: "turn:global.relay.metered.ca:80",
            username: "2b2719f9ca1ea7b6a7df3a2f",
            credential: "o5xajszcOs3pmr3X"
        },
        {
            urls: "turn:global.relay.metered.ca:80?transport=tcp",
            username: "2b2719f9ca1ea7b6a7df3a2f",
            credential: "o5xajszcOs3pmr3X"
        },
        {
            urls: "turn:global.relay.metered.ca:443",
            username: "2b2719f9ca1ea7b6a7df3a2f",
            credential: "o5xajszcOs3pmr3X"
        },
        {
            urls: "turns:global.relay.metered.ca:443?transport=tcp",
            username: "2b2719f9ca1ea7b6a7df3a2f",
            credential: "o5xajszcOs3pmr3X"
        }
    ]
}

// ─── UI helpers ───────────────────────────────────────────────────────────────
function updateStatus(state, text) {
    document.getElementById('status-dot').className = 'status-dot ' + state
    document.getElementById('status-text').textContent = text
}

function hidePlaceholder() {
    document.getElementById('placeholder').style.display = 'none'
}

function showPlaceholder(text) {
    document.getElementById('placeholder').style.display = 'flex'
    document.getElementById('placeholder-text').textContent = text
}

function leaveSession() {
    window.location.href = '/session/join'
}

// ─── entry point ──────────────────────────────────────────────────────────────
window.onload = async () => {

    // teacher — get camera and mic immediately on page load
    // student — no camera needed, just wait
    if (role === 'teacher') {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: true,
                video: true
            })
            const selfVideo = document.getElementById('self-video')
            if (selfVideo) selfVideo.srcObject = stream

        } catch (err) {
            console.error('Camera access failed:', err)
            updateStatus('error', 'camera access denied')
            return
        }
    }

    // connect websocket for both teacher and student
    initializeWebSocket()
}

// ─── websocket ────────────────────────────────────────────────────────────────
function initializeWebSocket() {
    const protocol  = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host      = window.location.host
    const socketUrl = `${protocol}//${host}/session/ws/${encodeURIComponent(session_id)}?role=${encodeURIComponent(role)}&name=${encodeURIComponent(user_name)}`

    updateStatus('connecting', 'connecting...')
    socket = new WebSocket(socketUrl)

    socket.onopen = async () => {
        // teacher starts WebRTC immediately — they have camera ready
        // student waits for "session-state" message from server
        // server sends state immediately after WebSocket connects
        if (role === 'teacher') {
            await startWebRTC()
        }
    }

    socket.onmessage = async (event) => {
        const data = JSON.parse(event.data)

        switch (data.type) {

            case 'session-state':
                // server tells us current state of session
                // this arrives immediately after WebSocket connects
                // and also when teacher joins/leaves later
                await handleSessionState(data.state)
                break

            case 'answer':
                // server responded to our offer — complete the handshake
                await handleAnswer(data.sdp)
                break

            case 'ice-candidate':
                // server found a network path — add it
                await handleIceCandidate(data.candidate)
                break

            default:
                console.warn('Unknown message type:', data.type)
        }
    }

    socket.onclose = () => {
        updateStatus('error', 'disconnected')
        console.log('WebSocket closed')
    }
}

// ─── session state handler ────────────────────────────────────────────────────
async function handleSessionState(state) {
    console.log('Session state:', state)

    if (state === 'waiting') {
        // teacher not here yet
        updateStatus('connecting', 'waiting for teacher...')
        showPlaceholder('Waiting for teacher to start the session...')

    } else if (state === 'live') {
        // teacher is online and streaming
        updateStatus('connected', 'session is live')

        if (role === 'student') {
            // student starts WebRTC now — teacher tracks are ready on server
            // if peerConnection exists already — close it and start fresh
            // this handles the case where student was waiting and teacher just joined
            if (peerConnection) {
                peerConnection.close()
                peerConnection = null
            }
            await startWebRTC()
        }

    } else if (state === 'ended') {
        // teacher left the session
        updateStatus('error', 'session has ended')
        showPlaceholder('Session has ended. Thank you for attending.')

        // clean up peer connection
        if (peerConnection) {
            peerConnection.close()
            peerConnection = null
        }
    }
}

// ─── webrtc ───────────────────────────────────────────────────────────────────
async function startWebRTC() {
    await setUpPeerConnection()
    await createOffer()
}

async function setUpPeerConnection() {
    peerConnection = new RTCPeerConnection(ICE_SERVERS)

    // when server finds network path — send to other side
    peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
            socket.send(JSON.stringify({
                type: 'ice-candidate',
                candidate: event.candidate
            }))
        }
    }

    // when server sends tracks to student — display them
    peerConnection.ontrack = (event) => {
        if (role === 'student') {
            const teacherVideo = document.getElementById('teacher-video')
            if (teacherVideo && event.streams[0]) {
                teacherVideo.srcObject = event.streams[0]
                hidePlaceholder()
                updateStatus('connected', 'receiving stream')
            }
        }
    }

    // teacher adds their camera and mic tracks
    // student adds nothing — only receives
    if (role === 'teacher' && stream) {
        stream.getTracks().forEach(track => {
            peerConnection.addTrack(track, stream)
        })
    }
}

async function createOffer() {
    const offer = await peerConnection.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: true
    })
    await peerConnection.setLocalDescription(offer)

    socket.send(JSON.stringify({
        type: 'offer',
        sdp: offer
    }))
}

async function handleAnswer(answer) {
    await peerConnection.setRemoteDescription(
        new RTCSessionDescription(answer)
    )
}

async function handleIceCandidate(candidate) {
    if (!peerConnection) return
    try {
        await peerConnection.addIceCandidate(
            new RTCIceCandidate(candidate)
        )
    } catch (err) {
        console.error('ICE candidate error:', err)
    }
}