let currentSlide = 0;
let slides = [];

/**
 * Render navigation dots for the gallery
 */
function renderDots() {
  const dotsContainer = document.querySelector(".dots");
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
  slider.style.transform = `translateX(-${index * 100}%)`;
  document.querySelector(".page-indicator").textContent = `${index + 1}/${slides.length}`;
  currentSlide = index;
  renderDots();
}

/**
 * Load boarding house details from backend
 */
async function loadBoardingHouse(id, university, studentId) {
  try {
    const response = await fetch(`/home/boardinghouse/${id}?university=${university}&student_id=${studentId}`);
    if (!response.ok) throw new Error("Failed to fetch details");
    const data = await response.json();

    // Name + location
    document.querySelector(".house-name").textContent = data.name;
    document.querySelector(".location").textContent = "📍 " + (data.location || "");

    // Phone
    if (data.phone_number) {
      document.querySelector(".action-icon.phone").href = `tel:${data.phone_number}`;
    }

    // Google Maps
    if (data.GPS_coordinates) {
      document.querySelector(".action-icon.google").href =
        `https://maps.google.com/?q=${data.GPS_coordinates.lat},${data.GPS_coordinates.lon}`;
    }

    // Yango
    if (data.yango_coordinates) {
      document.querySelector(".action-icon.yango").href =
        `https://yango.com/?coords=${data.yango_coordinates.lat},${data.yango_coordinates.lon}`;
    }

    // Bus stop (placeholder)
    document.querySelector(".action-icon.bus").href = "#";

    // Gallery
    const gallerySlider = document.querySelector(".gallery-slider");
    gallerySlider.innerHTML = "";
    slides = [];
    (data.gallery || []).forEach((item, i) => {
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

    // Auto cycle
    setInterval(() => {
      if (slides.length === 0) return;
      const next = (currentSlide + 1) % slides.length;
      showSlide(next);
    }, 5000);

    // Space overview
    document.querySelector(".space-description").textContent = data.space_description || "";

    // Conditions
    document.querySelector(".conditions").textContent = data.conditions || "";

    // Amenities
    const amenitiesList = document.querySelector(".amenities-list");
    amenitiesList.innerHTML = "";
    (data.amenities || []).forEach(a => {
      const li = document.createElement("li");
      li.textContent = a;
      amenitiesList.appendChild(li);
    });

    // Rooms
    const grid = document.querySelector(".rooms .grid");
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
      const badgeClass = r.status==='AVAILABLE'?'available':r.status==='UNAVAILABLE'?'unavailable':'not-supported';
      card.innerHTML = `
        <img src="${r.image || 'placeholder.jpg'}" alt="${r.type}">
        <div class="room-info">
          <div class="room-header">
            <p class="room-type">${r.type}</p>
            <span class="badge ${badgeClass}">${r.status || 'NOT SUPPORTED'}</span>
          </div>
          <p class="room-price">Price: ${r.price || 'N/A'}</p>
        </div>`;
      grid.appendChild(card);
    });

  } catch (err) {
    console.error(err);
    alert("Error loading boarding house details");
  }
}

// Example call (replace with real IDs)
loadBoardingHouse("house123", "universityX", "studentY");
