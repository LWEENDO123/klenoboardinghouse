document.getElementById("signupForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const body = {
    first_name: document.getElementById("first_name").value.trim(),
    last_name: document.getElementById("last_name").value.trim(),
    email: document.getElementById("email").value.trim(),
    password: document.getElementById("password").value.trim(),
    phone_number: document.getElementById("phone_number").value.trim(),
    university: document.getElementById("university").value.trim(),
  };

  try {
    const res = await fetch("https://klenoboardinghouse-production.up.railway.app/users/student_signup", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": "d17809df9e6c4e33801af1c5ee9d11da"
      },
      body: JSON.stringify(body)
    });

    const data = await res.json();
    if (res.ok) {
      document.getElementById("message").textContent = "Signup successful! Please login.";
      window.location.href = "login.html";
    } else {
      document.getElementById("message").textContent = data.detail || "Signup failed.";
    }
  } catch (err) {
    document.getElementById("message").textContent = "Error: " + err;
  }
});
