import { authorizedGet } from "./tokenManager.js";

let currentSlide = 0;
let slides = [];
const baseUrl = "https://klenoboardinghouse-production.up.railway.app";
const currentUserUniversity = localStorage.getItem("user_university") || ""; // fallback

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

function showSlide(index) {
  const slider = document.querySelector(".gallery-slider");
  if (!slider) return;
  slider.style.transform = `translateX(-${index * 100}%)`;
  const indicator = document.querySelector(".page-indicator");
  if (indicator) indicator.textContent = `${index + 1}/${slides.length}`;
  currentSlide = index;
  renderDots();
}

async function loadBoardingHouse(id, university, studentId) {
  try {
    if (!id || !studentId) {
      alert("Missing boarding house id or student id");
      return;
    }

    // ✅ Always send a valid university
    let uniToSend = university && university !== "default"
      ? university
      : (currentUserUniversity || "");

    if (!uniToSend) {
      alert("Missing university parameter");
      return;
    }

    const url = `${baseUrl}/home/boardinghouse/${encodeURIComponent(id)}?student_id=${encodeURIComponent(studentId)}&university=${encodeURIComponent(uniToSend)}`;

    console.log("[DEBUG] Fetching detail from:", url);
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

    // Populate UI
    document.querySelector(".house-name").textContent = data.name_boardinghouse || data.name || "";
    document.querySelector(".location").textContent = "📍 " + (data.location || "");

    const phoneAnchor = document.querySelector(".action-icon.phone");
    if (phoneAnchor && data.phone_number) phoneAnchor.href = `tel:${data.phone_number}`;

    const googleAnchor = document.querySelector(".action-icon.google");
    if (googleAnchor && data.GPS_coordinates?.lat && data.GPS_coordinates?.lon) {
      googleAnchor.href = `https://maps.google.com/?q=${data.GPS_coordinates.lat},${data.GPS_coordinates.lon}`;
    }

    const yangoAnchor = document.querySelector(".action-icon.yango");
    if (yangoAnchor && data.yango_coordinates?.lat && data.yango_coordinates?.lon) {
      yangoAnchor.href = `https://yango.com/?coords=${data.yango_coordinates.lat},${data.yango_coordinates.lon}`;
    }

    const busAnchor = document.querySelector(".action-icon.bus");
    if (busAnchor) busAnchor.href = "#";

    const gallerySlider = document.querySelector(".gallery-slider");
    if (gallerySlider) {
      gallerySlider.innerHTML = "";
      slides = [];
      (data.gallery || []).forEach(item => {
        const slide = document.createElement("div");
        slide.className = "slide";
        slide.innerHTML = item.type === "video"
          ? `<video controls src="${item.url}"></video>`
          : `<img src="${item.url}" alt="${item.caption || 'Gallery'}">`;
        gallerySlider.appendChild(slide);
        slides.push(slide);
      });
      if (slides.length > 0) showSlide(0);
      renderDots();
    }

    if (window._detailAutoCycleInterval) clearInterval(window._detailAutoCycleInterval);
    window._detailAutoCycleInterval = setInterval(() => {
      if (slides.length === 0) return;
      const next = (currentSlide + 1) % slides.length;
      showSlide(next);
    }, 5000);

    document.querySelector(".space-description").textContent = data.space_description || "";
    document.querySelector(".conditions").textContent = data.conditions || "";

    const amenitiesList = document.querySelector(".amenities-list");
    if (amenitiesList) {
      amenitiesList.innerHTML = "";
      (data.amenities || []).forEach(a => {
        const li = document.createElement("li");
        li.textContent = a;
        amenitiesList.appendChild(li);
      });
    }

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
        const card = document.createElement("div");
        card.className = "room-card";
        const badgeClass = (r.status?.toUpperCase() === 'AVAILABLE') ? 'available'
                         : (r.status?.toUpperCase() === 'UNAVAILABLE') ? 'unavailable'
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

// Parse query params
const params = new URLSearchParams(window.location.search);
const houseId = params.get("id");
const university = params.get("university");
const studentId = params.get("student_id");

if (houseId && studentId) {
  loadBoardingHouse(houseId, university, studentId);
} else {
  alert("Missing boarding house parameters in URL");
}
