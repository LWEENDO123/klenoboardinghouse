import { authorizedGet } from "./tokenManager.js";

let currentSlide = 0;
let slides = [];
const baseUrl = "https://klenoboardinghouse-production.up.railway.app";
const currentUserUniversity = localStorage.getItem("user_university") || ""; // fallback

/**
 * Render navigation dots for the gallery
 */
function renderDots() {
  const dotsContainer = document.querySelector(".dots");
  if (!dotsContainer) return;
  dotsContainer.innerHTML = "";
  slides.forEach((_, i) => {
    const dot = document.createElement("span");
    dot.className = "dot" + (i === currentSlide ? " active" : "");
    dot.addEventListener("click", () => showSlide(i));
    dotsContainer.appendChild(dot);
  });
}

/**
 * Show a specific slide in the gallery
 */
function showSlide(index) {
  const slider = document.querySelector(".gallery-slider");
  if (!slider) return;
  slider.style.transform = `translateX(-${index * 100}%)`;
  const indicator = document.querySelector(".page-indicator");
  if (indicator) indicator.textContent = `${index + 1}/${slides.length}`;
  currentSlide = index;
  renderDots();
}

/**
 * Load boarding house details from backend
 */
async function loadBoardingHouse(id, university, studentId) {
  try {
    if (!id || !studentId) {
      alert("Missing boarding house id or student id");
      return;
    }

    // Determine university to send: prefer query param, else currentUserUniversity, else omit
    let uniToSend = university && university !== "default" ? university : (currentUserUniversity || "");
    const uniQuery = uniToSend ? `&university=${encodeURIComponent(uniToSend)}` : "";
    const url = `${baseUrl}/home/boardinghouse/${encodeURIComponent(id)}?student_id=${encodeURIComponent(studentId)}${uniQuery}`;

    console.log("[DEBUG] Fetching detail from:", url);
    // Use authorizedGet so auth headers are included
    const res = await authorizedGet(url);
    console.log("[DEBUG] Detail response status:", res.status);

    if (!res.ok) {
      const errBody = await res.text().catch(() => "");
      console.error("[DEBUG] Detail fetch failed:", res.status, errBody);
      if (res.status === 404) {
        document.querySelector(".house-name").textContent = "Not found";
        document.querySelector(".space-description").textContent = "";
        return;
      }
      throw new Error(`Failed to fetch details: ${res.status}`);
    }

    const data = await res.json();
    console.log("[DEBUG] Detail JSON:", data);

    // Name + location
    document.querySelector(".house-name").textContent = data.name_boardinghouse || data.name || "";
    document.querySelector(".location").textContent = "📍 " + (data.location || "");

    // Phone
    const phoneAnchor = document.querySelector(".action-icon.phone");
    if (phoneAnchor && data.phone_number) {
      phoneAnchor.href = `tel:${data.phone_number}`;
    }

    // Google Maps
    const googleAnchor = document.querySelector(".action-icon.google");
    if (googleAnchor && data.GPS_coordinates && data.GPS_coordinates.lat && data.GPS_coordinates.lon) {
      googleAnchor.href = `https://maps.google.com/?q=${data.GPS_coordinates.lat},${data.GPS_coordinates.lon}`;
    }

    // Yango
    const yangoAnchor = document.querySelector(".action-icon.yango");
    if (yangoAnchor && data.yango_coordinates && data.yango_coordinates.lat && data.yango_coordinates.lon) {
      yangoAnchor.href = `https://yango.com/?coords=${data.yango_coordinates.lat},${data.yango_coordinates.lon}`;
    }

    // Bus stop (placeholder)
    const busAnchor = document.querySelector(".action-icon.bus");
    if (busAnchor) busAnchor.href = "#";

    // Gallery
    const gallerySlider = document.querySelector(".gallery-slider");
    if (gallerySlider) {
      gallerySlider.innerHTML = "";
      slides = [];
      (data.gallery || []).forEach(item => {
        const slide = document.createElement("div");
        slide.className = "slide";
        if (item.type === "video") {
          slide.innerHTML = `<video controls src="${item.url}"></video>`;
        } else {
          slide.innerHTML = `<img src="${item.url}" alt="${item.caption || 'Gallery'}">`;
        }
        gallerySlider.appendChild(slide);
        slides.push(slide);
      });
      if (slides.length > 0) showSlide(0);
      renderDots();
    }

    // Auto cycle (clear previous interval if any)
    if (window._detailAutoCycleInterval) clearInterval(window._detailAutoCycleInterval);
    window._detailAutoCycleInterval = setInterval(() => {
      if (slides.length === 0) return;
      const next = (currentSlide + 1) % slides.length;
      showSlide(next);
    }, 5000);

    // Space overview
    const spaceEl = document.querySelector(".space-description");
    if (spaceEl) spaceEl.textContent = data.space_description || "";

    // Conditions
    const condEl = document.querySelector(".conditions");
    if (condEl) condEl.textContent = data.conditions || "";

    // Amenities
    const amenitiesList = document.querySelector(".amenities-list");
    if (amenitiesList) {
      amenitiesList.innerHTML = "";
      (data.amenities || []).forEach(a => {
        const li = document.createElement("li");
        li.textContent = a;
        amenitiesList.appendChild(li);
      });
    }

    // Rooms
    const grid = document.querySelector(".rooms .grid");
    if (grid) {
      grid.innerHTML = "";
      const roomDefs = [
        {type:"12 Shared Room", price:data.price_12, status:data.sharedroom_12, image:data.image_12},
        {type:"6 Shared Room", price:data.price_6, status:data.sharedroom_6, image:data.image_6},
        {type:"5 Shared Room", price:data.price_5, status:data.sharedroom_5, image:data.image_5},
        {type:"4 Shared Room", price:data.price_4, status:data.sharedroom_4, image:data.image_4},
        {type:"3 Shared Room", price:data.price_3, status:data.sharedroom_3, image:data.image_3},
        {type:"2 Shared Room", price:data.price_2, status:data.sharedroom_2, image:data.image_2},
        {type:"Single Room", price:data.price_1, status:data.singleroom, image:data.image_1},
      ];
      roomDefs.forEach(r => {
        if (!r.type) return;
        const card = document.createElement("div");
        card.className = "room-card";
        const badgeClass = (r.status && r.status.toString().toUpperCase() === 'AVAILABLE') ? 'available'
                         : (r.status && r.status.toString().toUpperCase() === 'UNAVAILABLE') ? 'unavailable'
                         : 'not-supported';
        card.innerHTML = `
          <img src="${r.image || '/static/assets/images/placeholder.jpg'}" alt="${r.type}">
          <div class="room-info">
            <div class="room-header">
              <p class="room-type">${r.type}</p>
              <span class="badge ${badgeClass}">${r.status || 'NOT SUPPORTED'}</span>
            </div>
            <p class="room-price">Price: ${r.price || 'N/A'}</p>
          </div>`;
        grid.appendChild(card);
      });
    }

  } catch (err) {
    console.error(err);
    alert("Error loading boarding house details");
  }
}

// Parse query params from URL and load actual data
const params = new URLSearchParams(window.location.search);
const houseId = params.get("id");
const university = params.get("university");
const studentId = params.get("student_id");

// If university is empty string, treat as missing and let loadBoardingHouse fallback to currentUserUniversity
if (houseId && studentId) {
  loadBoardingHouse(houseId, university, studentId);
} else {
  alert("Missing boarding house parameters in URL");
}
