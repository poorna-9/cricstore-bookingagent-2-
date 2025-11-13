document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById("slots-section");
  const hiddenInput = document.getElementById('selectedSlotsInput');
  const dateInput = document.getElementById('slot-date'); 

  console.log("DEBUG loaded date input element:", dateInput);
  if (!container || !dateInput) {
    console.error("Missing container or date input");
    return;
  }

  console.log("Loaded date value:", dateInput.value); 

  const groundIdFromContainer = container.dataset.groundid;
  const currentUserId = parseInt(container.dataset.userid, 10) || null;
  let selectedSlots = new Set();

  function updateSelectedSlots() {
    hiddenInput.value = Array.from(selectedSlots).join(',');
  }
  container.addEventListener("click", function (e) {
    const slot = e.target.closest(".slot");
    if (!slot) return;

    const slotId = slot.dataset.slotid;
    const groundId = groundIdFromContainer;
    const date = dateInput.value; 
    console.log("DEBUG trying to send:", { groundId, slotId, date });

    if (!date) {
      alert("Please select a date first.");
      return;
    }
    if (slot.classList.contains("booked") || (slot.classList.contains("reserved") && !slot.classList.contains("my-reserved"))) {
      return;
    }

    const body = new URLSearchParams();
    body.append('ground_id', groundId);
    body.append('slot_id', slotId);
    body.append('date', date);

    fetch("/bookings/reserveslot/", {
      method: "POST",
      headers: {
        "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString()
    })
      .then(res => res.json())
      .then(data => {
        console.log("DEBUG server response:", data);
        if (data.success) {
          if (data.action === "selected") {
            slot.classList.add("my-reserved");
            slot.classList.remove("available");
            selectedSlots.add(slotId);
          } else if (data.action === "unselected") {
            slot.classList.remove("my-reserved");
            slot.classList.add("available");
            selectedSlots.delete(slotId);
          }
          updateSelectedSlots();
        } else {
          alert(data.message || "Action failed");
        }
      })
      .catch(err => {
        console.error("Fetch error:", err);
        alert("Network error");
      });
  });

  dateInput.addEventListener('change', function () {
    const selectedDate = this.value;
    if (!selectedDate) return;
    window.location.href = `/bookings/grounddetail/${groundIdFromContainer}/?date=${selectedDate}`;
  });
  function refreshReservedSlots() {
    const date = dateInput.value;
    const groundId = groundIdFromContainer;
    if (!date) return;

    fetch(`/bookings/get_reserved_slots/?ground_id=${groundId}&date=${date}`)
      .then(res => res.json())
      .then(data => {
        const userReserved = new Set((data.user_reserved || []).map(String));
        const othersReserved = new Set((data.others_reserved || []).map(String));
        const bookedSet = new Set((data.booked || []).map(String));

        selectedSlots = new Set(userReserved);
        updateSelectedSlots();

        container.querySelectorAll(".slot").forEach(slot => {
          const id = slot.dataset.slotid;
          if (bookedSet.has(id)) {
            slot.classList.add("booked");
            slot.classList.remove("available", "reserved", "my-reserved");
          } else if (userReserved.has(id)) {
            slot.classList.add("my-reserved");
            slot.classList.remove("available", "reserved", "booked");
          } else if (othersReserved.has(id)) {
            slot.classList.add("reserved");
            slot.classList.remove("available", "my-reserved", "booked");
          } else {
            slot.classList.remove("reserved", "my-reserved", "booked");
            slot.classList.add("available");
          }
        });
      })
      .catch(err => console.error("refreshReservedSlots error:", err));
  }

  setInterval(refreshReservedSlots, 5000);
  refreshReservedSlots();
});
