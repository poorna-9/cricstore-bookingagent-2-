(function () {
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatMessages = document.getElementById("chatMessages");
  const quickReplies = document.getElementById("quickReplies");
  const agentContent = document.getElementById("agentContent");
  const modeLabel = document.getElementById("modeLabel");
  const sendBtn = document.getElementById("sendBtn");

  let currentMode = null;

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
      btn.textContent = option;
      btn.onclick = () => handleQuickReply(option);
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
      "Normal Booking",
      "Tournament Booking",
      "Cancel Booking",
      "Reschedule Booking",
    ]);
  }

  function handleQuickReply(text) {
    const modeMap = {
      "Normal Booking": "normal_booking",
      "Tournament Booking": "tournament_booking",
      "Cancel Booking": "cancellation",
      "Reschedule Booking": "reschedule",
    };

    if (!currentMode && modeMap[text]) {
      currentMode = modeMap[text];
      addUserMessage(text);
      clearQuickReplies();

      modeLabel.textContent = `Mode: ${text}`;
      addBotMessage(`✅ ${text} selected.`);
      addBotMessage("Tell me your requirement.");
      enableChat();
      return;
    }

    sendQuery(text);
  }

  async function sendQuery(query) {
    if (!query || !currentMode) return;

    addUserMessage(query);
    chatInput.value = "";

    try {
      const response = await fetch(
        `${CHATBOT_URL}?query=${encodeURIComponent(query)}&mode=${currentMode}`,
        {
          method: "GET",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        }
      );

      const contentType = response.headers.get("content-type") || "";

      if (contentType.includes("text/html")) {
        const html = await response.text();
        addBotMessage("Showing results on the right 👉");
        agentContent.innerHTML = html;
        return;
      }

      const data = await response.json();

      if (data.message) {
        addBotMessage(data.message);
      }

      if (data.options) {
        showQuickReplies(data.options.map(o => o.text));
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

})();
