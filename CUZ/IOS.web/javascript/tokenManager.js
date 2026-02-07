const baseUrl = "https://klenoboardinghouse-production.up.railway.app";
const apiKey = "d17809df9e6c4e33801af1c5ee9d11da"; // same as Core.apiKey in Flutter

// -------------------------
// Storage helpers
// -------------------------
function getAccessToken() { return localStorage.getItem("access_token"); }
function getRefreshToken() { return localStorage.getItem("refresh_token"); }
function getStudentId() { return localStorage.getItem("user_id"); }
function getUniversity() { return localStorage.getItem("university"); }
function getDeviceToken() { return localStorage.getItem("device_token"); }

function saveTokens(access, refresh) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearAll() {
  localStorage.clear();
}

// -------------------------
// Refresh logic
// -------------------------
async function refreshTokens() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${baseUrl}/users/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-api-key": apiKey,
      },
      body: new URLSearchParams({ refresh_token: refreshToken }),
    });

    if (res.ok) {
      const data = await res.json();
      saveTokens(data.access_token, data.refresh_token);
      return true;
    } else {
      clearAll();
      return false;
    }
  } catch (err) {
    console.error("refreshTokens error:", err);
    return false;
  }
}

// -------------------------
// Forced logout detection
// -------------------------
function isForcedLogout(bodyText, status) {
  const lower = (bodyText || "").toLowerCase();
  return (
    status === 401 &&
    (lower.includes("another device") ||
     lower.includes("force logout") ||
     lower.includes("logged out") ||
     lower.includes("session invalidated"))
  );
}

// -------------------------
// Header builder
// -------------------------
async function getValidAccessToken() {
  let token = getAccessToken();
  if (!token) {
    const ok = await refreshTokens();
    token = ok ? getAccessToken() : null;
  }
  return token;
}

async function buildHeaders(extra = {}) {
  const token = await getValidAccessToken();
  if (!token) throw new Error("No valid access token");
  const deviceToken = getDeviceToken();
  return {
    Authorization: "Bearer " + token,
    "x-api-key": apiKey,
    "Content-Type": "application/json",
    ...(deviceToken ? { "x-device-token": deviceToken } : {}),
    ...extra,
  };
}

// -------------------------
// Authorized request helpers
// -------------------------
export async function authorizedGet(url) {
  let res = await fetch(url, { headers: await buildHeaders() });
  const bodyText = await res.clone().text();

  if (isForcedLogout(bodyText, res.status)) {
    clearAll();
    alert("You’ve been logged out because your account was used on another device");
    window.location.href = "login.html";
    return res;
  }

  if (res.status === 401 && await refreshTokens()) {
    res = await fetch(url, { headers: await buildHeaders() });
  }
  return res;
}

export async function authorizedPost(url, body) {
  let res = await fetch(url, {
    method: "POST",
    headers: await buildHeaders(),
    body: JSON.stringify(body),
  });
  const bodyText = await res.clone().text();

  if (isForcedLogout(bodyText, res.status)) {
    clearAll();
    alert("You’ve been logged out because your account was used on another device");
    window.location.href = "login.html";
    return res;
  }

  if (res.status === 401 && await refreshTokens()) {
    res = await fetch(url, {
      method: "POST",
      headers: await buildHeaders(),
      body: JSON.stringify(body),
    });
  }
  return res;
}

export async function authorizedPut(url, body) {
  let res = await fetch(url, {
    method: "PUT",
    headers: await buildHeaders(),
    body: JSON.stringify(body),
  });
  const bodyText = await res.clone().text();

  if (isForcedLogout(bodyText, res.status)) {
    clearAll();
    alert("You’ve been logged out because your account was used on another device");
    window.location.href = "login.html";
    return res;
  }

  if (res.status === 401 && await refreshTokens()) {
    res = await fetch(url, {
      method: "PUT",
      headers: await buildHeaders(),
      body: JSON.stringify(body),
    });
  }
  return res;
}

export async function authorizedDelete(url) {
  let res = await fetch(url, {
    method: "DELETE",
    headers: await buildHeaders(),
  });
  const bodyText = await res.clone().text();

  if (isForcedLogout(bodyText, res.status)) {
    clearAll();
    alert("You’ve been logged out because your account was used on another device");
    window.location.href = "login.html";
    return res;
  }

  if (res.status === 401 && await refreshTokens()) {
    res = await fetch(url, {
      method: "DELETE",
      headers: await buildHeaders(),
    });
  }
  return res;
}
