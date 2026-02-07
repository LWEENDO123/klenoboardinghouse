document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();
  const university = document.getElementById("university").value.trim();

  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);

  try {
    const res = await fetch(`${baseUrl}/users/login?university=${university}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-api-key": apiKey
      },
      body: formData.toString()
    });

    const data = await res.json();
    if (res.ok) {
      document.getElementById("message").textContent = "Login successful!";

      // Save tokens and context to localStorage
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      localStorage.setItem("role", data.role);
      localStorage.setItem("user_id", data.user_id);
      localStorage.setItem("university", data.university);

      // If backend returns a device_token, save it too
      if (data.device_token) {
        localStorage.setItem("device_token", data.device_token);
      }

      // 🔹 Register device immediately after login
      try {
        await authorizedPost(`${baseUrl}/device/register`, {
          university: data.university,
          user_id: data.user_id,
          role: data.role,
          device_token: localStorage.getItem("device_token") || "web-" + Date.now(),
          platform: "web"
        });
        console.log("Device registered successfully");
      } catch (err) {
        console.error("Device registration failed:", err);
      }

      // Redirect to homepage
      window.location.href = "homepage.html";
    } else {
      document.getElementById("message").textContent = data.detail || "Login failed.";
    }
  } catch (err) {
    document.getElementById("message").textContent = "Error: " + err;
  }
});
