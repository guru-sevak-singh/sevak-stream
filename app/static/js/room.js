let socket = null;
let peerConnection = null;
let stream = null;

const url_perms = new URLSearchParams(window.location.search);
const role = url_perms.get('role');
const user_name = url_perms.get('name');

const path = window.location.pathname
const session_id = path.match(/\/session\/([^\/]+)\//)[1]

if (role === 'teacher') {
    document.getElementById('rec-indicator').classList.add('visible')
    document.getElementById('self-view-wrap').classList.add('visible')
    document.getElementById('placeholder-text').textContent = 'Starting your camera...'
}


function updateStatus(state, text) {
    const dot = document.getElementById('status-dot')
    const txt = document.getElementById('status-text')
    dot.className = 'status-dot ' + state
    txt.textContent = text
}

function hidePlaceholder() {
    document.getElementById('placeholder').style.display = 'none'
}

function leaveSession() {
    window.location.href = '/session/join'
}

window.onload = async () => {
    await InitilizeRoom();
}

async function InitilizeRoom() {
    if (role === 'teacher') {
        stream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: true
        })
        const selfVideo = document.getElementById('self-video');
        if (selfVideo) {
            selfVideo.srcObject = stream;
        }
    }

    InitilizeWebSocket();
}

function InitilizeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const socket_url = `${protocol}//${host}/session/ws/${encodeURIComponent(session_id)}/?role=${encodeURIComponent(role)}&name=${encodeURIComponent(user_name)}`

    updateStatus('connecting', 'connecting...')
    socket = new WebSocket(socket_url);

    socket.onopen = async (event) => {
        await setUpPeerConnection();
        await createOffer();
        updateStatus('connected', 'connected');
    };

    socket.onmessage = async (event) => {
        const eventData = JSON.parse(event.data);
        const type = eventData.type;

        switch (type) {
            case "answer":
                const answer = eventData.sdp;
                await handleAnswer(answer);
                break;

            case "ice-candidate":
                const candidate = eventData.candidate;
                await handleIceCandidate(candidate);
                break;

            default:
                console.warn("Unknown message type: ", type);
                break;
        }
    };

    socket.onclose = (event) => {
        console.log('socket is going to close....');
        console.error('event => ', event);
        updateStatus('error', 'disconnected')
    };
}

async function setUpPeerConnection() {

    peerConnection = new RTCPeerConnection(
        {
            iceServers: [
                {
                    urls: "stun:stun.relay.metered.ca:80",
                },
                {
                    urls: "turn:global.relay.metered.ca:80",
                    username: "2b2719f9ca1ea7b6a7df3a2f",
                    credential: "o5xajszcOs3pmr3X",
                },
                {
                    urls: "turn:global.relay.metered.ca:80?transport=tcp",
                    username: "2b2719f9ca1ea7b6a7df3a2f",
                    credential: "o5xajszcOs3pmr3X",
                },
                {
                    urls: "turn:global.relay.metered.ca:443",
                    username: "2b2719f9ca1ea7b6a7df3a2f",
                    credential: "o5xajszcOs3pmr3X",
                },
                {
                    urls: "turns:global.relay.metered.ca:443?transport=tcp",
                    username: "2b2719f9ca1ea7b6a7df3a2f",
                    credential: "o5xajszcOs3pmr3X",
                },
            ]
        }
    );

    peerConnection.onicecandidate = async (event) => {
        if (event.candidate) {
            socket.send(JSON.stringify({
                type: "ice-candidate",
                candidate: event.candidate
            }))
        }
    };

    peerConnection.ontrack = (event) => {
        if (role === 'student') {
            const teacherVideo = document.getElementById('teacher-video');
            if (teacherVideo) {
                hidePlaceholder()
                teacherVideo.srcObject = event.streams[0];
            }
        }
    }

    if (role === 'teacher' && stream) {
        stream.getTracks().forEach((track) => {
            peerConnection.addTrack(track, stream);
        });

    }

}

async function createOffer() {
    const offer = await peerConnection.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: true
    });

    await peerConnection.setLocalDescription(offer);

    socket.send(JSON.stringify({
        type: "offer",
        sdp: offer
    }));
}

async function handleAnswer(answer) {
    await peerConnection.setRemoteDescription(
        new RTCSessionDescription(answer)
    );
}

async function handleIceCandidate(candidate) {
    await peerConnection.addIceCandidate(
        new RTCIceCandidate(candidate)
    );
}