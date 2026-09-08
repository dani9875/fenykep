document.getElementById("contact-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("cf-error");
  errorEl.style.display = "none";

  const payload = {
    firstName: document.getElementById("cf-first").value.trim(),
    lastName: document.getElementById("cf-last").value.trim(),
    email: document.getElementById("cf-email").value.trim(),
    phone: document.getElementById("cf-phone").value.trim(),
    subject: document.getElementById("cf-subject").value.trim(),
    message: document.getElementById("cf-message").value.trim(),
  };

  const btn = document.getElementById("cf-submit");
  btn.disabled = true;
  btn.textContent = "Küldés…";

  try {
    await Api.sendContactMessage(payload);
    document.getElementById("contact-form").style.display = "none";
    document.getElementById("cf-success").style.display = "block";
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = "block";
    btn.disabled = false;
    btn.textContent = "Üzenet küldése";
  }
});
