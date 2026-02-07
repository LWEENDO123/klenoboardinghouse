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

  try {
    const res = await authorizedGet(url);
    const data = await res.json();

    if (res.ok) {
      const houses = data.data || [];
      houses.forEach(h => renderHouse(h));
      page++;
      hasMore = houses.length === limit;
    } else {
      console.error("Failed:", data);
    }
  } catch (err) {
    console.error("Error:", err);
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
    window.location.href = \`detail.html?id=${house.id}&university=${selectedUniversity || ''}&student_id=${studentId}\`;
  });

  document.getElementById("houseList").appendChild(card);
}

// Filter buttons
document.querySelectorAll(".filter").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedFilter = btn.dataset.filter;
    fetchHouses(true);
  });
});

// University dropdown
document.getElementById("universitySelect").addEventListener("change", e => {
  selectedUniversity = e.target.value;
  fetchHouses(true);
});

// Infinite scroll
window.addEventListener("scroll", () => {
  if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
    fetchHouses();
  }
});

// Initial load
fetchHouses();
