let authMode = "login";
let loggedInUser = "";
let currentUser = null;
let currentSuggestions = [];
let accuracyChart = null;
let isSending = false;
let debounceTimer = null;
let validationSequence = 0;
let latestValidationApplied = 0;

const chatUsers = [
    { name: "Alice Johnson", tag: "@alice", initials: "AJ", color: "#a855f7" },
    { name: "Bob Smith", tag: "@bob", initials: "BS", color: "#22c55e" },
    { name: "Carol Williams", tag: "@carol", initials: "CW", color: "#f97316" },
    { name: "David Brown", tag: "@david", initials: "DB", color: "#ec4899" },
    { name: "Emma Davis", tag: "@emma", initials: "ED", color: "#6366f1" }
];

document.addEventListener("DOMContentLoaded", () => {
    const msgInput = document.getElementById("msg");
    const sendBtn = document.getElementById("sendBtn");

    msgInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            checkMessage();
        }, 250);
    });

    msgInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !sendBtn.disabled) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener("click", sendMessage);
});

function switchAuth(mode) {
    authMode = mode;
    document.getElementById("loginTab").classList.toggle("active", mode === "login");
    document.getElementById("signupTab").classList.toggle("active", mode === "signup");
    document.getElementById("authBtn").innerText = mode === "login" ? "Sign In" : "Sign Up";
    document.getElementById("authStatus").innerText = "";
}

async function submitAuth() {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value.trim();

    if (!username || !password) {
        document.getElementById("authStatus").innerText = "Enter username and password.";
        return;
    }

    const endpoint = authMode === "login" ? "/login" : "/signup";

    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
            cache: "no-store"
        });

        const data = await response.json();

        if (data.status === "ok") {
            if (authMode === "signup") {
                document.getElementById("authStatus").innerText = "Signup successful. Please sign in.";
                switchAuth("login");
                return;
            }

            loggedInUser = data.username || username;

            document.getElementById("profileName").innerText = loggedInUser;
            document.getElementById("profileHandle").innerText = "@" + loggedInUser.toLowerCase().replace(/\s+/g, "_");
            document.getElementById("profileAvatar").innerText = loggedInUser.charAt(0).toUpperCase();

            document.getElementById("authPage").classList.add("hidden");
            document.getElementById("appPage").classList.remove("hidden");

            renderUsers();
        } else {
            document.getElementById("authStatus").innerText = data.message || "Failed.";
        }
    } catch (error) {
        document.getElementById("authStatus").innerText = "Server error.";
    }
}

function renderUsers() {
    const list = document.getElementById("userList");
    list.innerHTML = "";

    chatUsers.forEach(user => {
        const div = document.createElement("div");
        div.className = "user-item";
        div.dataset.name = user.name;
        div.innerHTML = `
            <div class="user-avatar" style="background:${user.color}">${user.initials}</div>
            <div class="user-text">
                <h4>${user.name}</h4>
                <p>${user.tag}</p>
            </div>
        `;
        div.onclick = () => selectUser(user);
        list.appendChild(div);
    });
}

async function selectUser(user) {
    currentUser = user;

    document.querySelectorAll(".user-item").forEach(item => {
        item.classList.toggle("active", item.dataset.name === user.name);
    });

    document.getElementById("welcomePanel").classList.add("hidden");
    document.getElementById("chatPanel").classList.remove("hidden");

    document.getElementById("chatUserName").innerText = user.name;
    document.getElementById("chatUserTag").innerText = user.tag;
    document.getElementById("chatAvatar").innerText = user.initials;
    document.getElementById("chatAvatar").style.background = user.color;

    document.getElementById("msg").value = "";
    document.getElementById("sendBtn").disabled = true;
    document.getElementById("sendBtn").innerText = "Send";

    document.getElementById("predictInfo").classList.add("hidden");
    document.getElementById("predictInfo").innerHTML = "";

    document.getElementById("suggestionArea").classList.add("hidden");
    document.getElementById("suggestionArea").innerHTML = "";

    currentSuggestions = [];
    await loadMessages();
}

async function loadMessages() {
    if (!loggedInUser || !currentUser) return;

    const response = await fetch(
        `/messages/${encodeURIComponent(loggedInUser)}/${encodeURIComponent(currentUser.name)}`,
        { cache: "no-store" }
    );
    const data = await response.json();

    const box = document.getElementById("messages");
    box.innerHTML = "";

    if (data.status === "ok" && data.messages.length > 0) {
        data.messages.forEach(item => {
            const div = document.createElement("div");
            div.className = `message ${item.sender === loggedInUser ? "sent" : "received"}`;
            div.innerText = item.message;
            box.appendChild(div);
        });
    } else {
        const div = document.createElement("div");
        div.className = "message system";
        div.innerText = "Start chatting. Toxic words must be replaced before sending.";
        box.appendChild(div);
    }

    box.scrollTop = box.scrollHeight;
}

async function checkMessage() {
    const input = document.getElementById("msg");
    const sendBtn = document.getElementById("sendBtn");
    const predictInfo = document.getElementById("predictInfo");
    const suggestionArea = document.getElementById("suggestionArea");
    const text = input.value.trim();

    if (!currentUser || !text) {
        sendBtn.disabled = true;
        predictInfo.classList.add("hidden");
        predictInfo.innerHTML = "";
        suggestionArea.classList.add("hidden");
        suggestionArea.innerHTML = "";
        currentSuggestions = [];
        return;
    }

    const currentValidation = ++validationSequence;
    sendBtn.disabled = true;

    try {
        const response = await fetch("/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text }),
            cache: "no-store"
        });

        const data = await response.json();

        if (currentValidation < latestValidationApplied) {
            return;
        }
        latestValidationApplied = currentValidation;

        currentSuggestions = data.suggestions || [];

        predictInfo.classList.remove("hidden");
        predictInfo.innerHTML = `Toxicity probability: ${(Number(data.probability) * 100).toFixed(2)}%`;

        if (currentSuggestions.length > 0) {
            suggestionArea.classList.remove("hidden");
            suggestionArea.innerHTML = `
                <div class="suggestion-title">Replace these toxic words before sending:</div>
                ${currentSuggestions.map(item => `
                    <button type="button" class="suggestion-chip"
                        onclick='replaceWord(${JSON.stringify(item.bad_word)}, ${JSON.stringify(item.good_word)})'>
                        ${escapeHtml(item.bad_word)} → ${escapeHtml(item.good_word)}
                    </button>
                `).join("")}
            `;
        } else {
            suggestionArea.classList.add("hidden");
            suggestionArea.innerHTML = "";
        }

        sendBtn.disabled = !data.can_send;
    } catch (error) {
        sendBtn.disabled = true;
        predictInfo.classList.remove("hidden");
        predictInfo.innerHTML = "Prediction error.";
    }
}

function replaceWord(bad, good) {
    const input = document.getElementById("msg");
    const escapedBad = bad.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`\\b${escapedBad}\\b`, "ig");
    input.value = input.value.replace(regex, good);
    checkMessage();
}

async function sendMessage() {
    const sendBtn = document.getElementById("sendBtn");
    const text = document.getElementById("msg").value.trim();

    if (!text || !currentUser || isSending || sendBtn.disabled) {
        return;
    }

    isSending = true;
    sendBtn.disabled = true;
    sendBtn.innerText = "Sending...";

    try {
        const response = await fetch("/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: loggedInUser,
                receiver: currentUser.name,
                message: text
            }),
            cache: "no-store"
        });

        const data = await response.json();

        if (data.status === "ok") {
            const box = document.getElementById("messages");
            box.innerHTML = "";

            data.messages.forEach(item => {
                const div = document.createElement("div");
                div.className = `message ${item.sender === loggedInUser ? "sent" : "received"}`;
                div.innerText = item.message;
                box.appendChild(div);
            });

            document.getElementById("msg").value = "";
            document.getElementById("suggestionArea").classList.add("hidden");
            document.getElementById("suggestionArea").innerHTML = "";
            document.getElementById("predictInfo").classList.add("hidden");
            document.getElementById("predictInfo").innerHTML = "";
            currentSuggestions = [];
            box.scrollTop = box.scrollHeight;
        } else {
            alert(data.message || "Blocked.");
        }
    } catch (error) {
        alert("Send failed.");
    } finally {
        isSending = false;
        sendBtn.innerText = "Send";
        checkMessage();
    }
}

async function loadAccuracyGraph() {
    try {
        const response = await fetch("/accuracy", { cache: "no-store" });
        const data = await response.json();

        const accuracy = Number(data.accuracy_percent || 0);
        const errorRate = Math.max(0, 100 - accuracy);

        document.getElementById("accuracyText").innerText = `Accuracy: ${accuracy.toFixed(2)}%`;

        const ctx = document.getElementById("accuracyChart").getContext("2d");

        if (accuracyChart) {
            accuracyChart.destroy();
        }

        accuracyChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: ["Accuracy", "Error Rate"],
                datasets: [{
                    label: "Model Performance (%)",
                    data: [accuracy, errorRate],
                    backgroundColor: ["#3568d4", "#f97316"],
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
    } catch (error) {
        document.getElementById("accuracyText").innerText = "Unable to load graph.";
    }
}

function escapeHtml(text) {
    return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function logoutUser() {
    loggedInUser = "";
    currentUser = null;
    currentSuggestions = [];
    isSending = false;

    document.getElementById("username").value = "";
    document.getElementById("password").value = "";
    document.getElementById("msg").value = "";
    document.getElementById("authStatus").innerText = "";

    document.getElementById("chatPanel").classList.add("hidden");
    document.getElementById("welcomePanel").classList.remove("hidden");
    document.getElementById("appPage").classList.add("hidden");
    document.getElementById("authPage").classList.remove("hidden");
}