(function () {
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatMessages = document.getElementById("chatMessages");
  const quickReplies = document.getElementById("quickReplies");
  const agentContent = document.getElementById("agentContent");
  const modeLabel = document.getElementById("modeLabel");
  const sendBtn = document.getElementById("sendBtn");

  let currentMode = null;

  let pendingRequiredFields = [];

  function addUserMessage(text) {
    const msg = document.createElement("div");
    msg.className = "message user";
    msg.textContent = text;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function addBotMessage(text) {
    const msg = document.createElement("div");
    msg.className = "message bot";
    msg.textContent = text;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function clearQuickReplies() {
    quickReplies.innerHTML = "";
  }

  function showQuickReplies(options = []) {
    clearQuickReplies();
    options.forEach((option) => {
      const btn = document.createElement("button");
      btn.className = "quick-reply";
      btn.textContent = option.text;
      btn.onclick = () => handleModeSelection(option.text);
      quickReplies.appendChild(btn);
    });
  }

  function enableChat() {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }

  function showModeSelection() {
    addBotMessage("What would you like to do today?");
    showQuickReplies([
      { text: "Normal Booking" },
      { text: "Tournament Booking" },
      { text: "Cancel Booking" },
      { text: "Reschedule Booking" },
    ]);
  }

  function handleModeSelection(text) {
    const modeMap = {
      "Normal Booking": "normal_booking",
      "Tournament Booking": "tournament",
      "Cancel Booking": "cancellation",
      "Reschedule Booking": "reschedule",
    };

    currentMode = modeMap[text];
    addUserMessage(text);
    clearQuickReplies();

    modeLabel.textContent = `Mode: ${text}`;
    addBotMessage(`${text} selected.`);
    addBotMessage("Tell me your requirement.");
    enableChat();
  }

  async function sendQuery(query, bookingId = null) {
    if (!currentMode) return;

    if (query) {
      addUserMessage(query);
      chatInput.value = "";
    }

    const params = new URLSearchParams({
      mode: currentMode,
      query: query || "",
    });

    if (pendingRequiredFields.length > 0) {
      params.append("required_fields", JSON.stringify(pendingRequiredFields));
    }

    if (bookingId) {
      params.append("booking_id", bookingId);
    }

    try {
      const response = await fetch(`${CHATBOT_URL}?${params.toString()}`, {
        method: "GET",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });

      const contentType = response.headers.get("content-type") || "";

      if (contentType.includes("text/html")) {
        const html = await response.text();
        addBotMessage("Showing results on the right 👉");
        agentContent.innerHTML = html;
        return;
      }

      const data = await response.json();

      if (Array.isArray(data.required_fields)) {
        pendingRequiredFields = data.required_fields;
      } else {
        pendingRequiredFields = [];
      }

      console.log("Pending Required Fields:", pendingRequiredFields);

      if (data.message) {
        addBotMessage(data.message);
      }

      if (data.options) {
        showQuickReplies(data.options);
      } else {
        enableChat();
      }

    } catch (err) {
      console.error(err);
      addBotMessage("Something went wrong. Please try again.");
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendQuery(chatInput.value.trim());
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event("submit"));
    }
  });

  addBotMessage("Hi! I'm your Booking Agent 🤖");
  showModeSelection();

  quickReplies.addEventListener("click", (e) => {
    if (e.target.classList.contains("quick-reply")) {
      handleModeSelection(e.target.textContent);
    }
  });
})();
