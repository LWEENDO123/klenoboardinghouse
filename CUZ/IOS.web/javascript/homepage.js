import { authorizedGet } from "./tokenManager.js";  // make sure this path is correct

let page = 1;
const limit = 10;
let hasMore = true;
let isLoading = false;
let selectedFilter = "all";
let selectedUniversity = "";
const studentId = localStorage.getItem("user_id");
const baseUrl = "https://klenoboardinghouse-production.up.railway.app";

async function fetchHouses(refresh = false) {
  if (isLoading || !hasMore) return;
  isLoading = true;
  document.getElementById("loader").style.display = "block";

  if (refresh) {
    page = 1;
    document.getElementById("houseList").innerHTML = "";
    hasMore = true;
  }

  const scope = selectedUniversity ? "scoped" : "default";
  const uniParam = selectedUniversity ? `&university=${selectedUniversity}` : "";
  const url = `${baseUrl}/home?student_id=${studentId}${uniParam}&scope=${scope}&page=${page}&limit=${limit}&filter=${selectedFilter}`;

  console.log("[DEBUG] Fetching houses from:", url);

  try {
    const res = await authorizedGet(url);
    console.log("[DEBUG] Response status:", res.status);

    const data = await res.json();
    console.log("[DEBUG] Response JSON:", data);

    if (res.ok) {
      const houses = data.data || [];
      console.log("[DEBUG] Houses array length:", houses.length);

      houses.forEach(h => {
        console.log("[DEBUG] Rendering house:", h);
        renderHouse(h);
      });

      page++;
      hasMore = houses.length === limit;
      console.log("[DEBUG] hasMore:", hasMore, "next page:", page);
    } else {
      console.error("[DEBUG] Failed response:", data);
    }
  } catch (err) {
    console.error("[DEBUG] Error fetching houses:", err);
  } finally {
    isLoading = false;
    document.getElementById("loader").style.display = "none";
  }
}

function renderHouse(house) {
  const card = document.createElement("div");
  card.className = "house-card";

  // Gender badge
  let genderIcon = "both.png";
  if (house.gender) {
    const g = house.gender.toLowerCase();
    if (g === "male") genderIcon = "male.png";
    else if (g === "female") genderIcon = "female.png";
    else if (g === "mixed") genderIcon = "both.png";
  }

  // ✅ Use backend URL directly, only fallback if empty
  const coverImage = house.cover_image && house.cover_image.startsWith("http")
    ? house.cover_image
    : "https://via.placeholder.com/400x200";

  console.log("[DEBUG] coverImage:", coverImage);

  card.innerHTML = `
    <img src="${coverImage}" alt="${house.name_boardinghouse}">
    <div class="info">
      <div>
        <h3>${house.name_boardinghouse}</h3>
        <p>📍 ${house.location || ''}</p>
      </div>
      <div class="gender-badge">
        <img src="assets/images/icons/${genderIcon}" alt="${house.gender || 'both'}">
      </div>
    </div>
  `;

  card.addEventListener("click", () => {
    console.log("[DEBUG] Card clicked:", house.id);
    window.location.href = `detail.html?id=${house.id}&university=${selectedUniversity || ''}&student_id=${studentId}`;
  });

  document.getElementById("houseList").appendChild(card);
  console.log("[DEBUG] Card appended for:", house.name_boardinghouse);
}

// Filter buttons
document.querySelectorAll(".filter").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedFilter = btn.dataset.filter;
    console.log("[DEBUG] Filter selected:", selectedFilter);
    fetchHouses(true);
  });
});

// University dropdown
document.getElementById("universitySelect").addEventListener("change", e => {
  selectedUniversity = e.target.value;
  console.log("[DEBUG] University selected:", selectedUniversity);
  fetchHouses(true);
});

// Infinite scroll
window.addEventListener("scroll", () => {
  if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
    console.log("[DEBUG] Triggering infinite scroll fetch");
    fetchHouses();
  }
});

// Initial load
fetchHouses();
