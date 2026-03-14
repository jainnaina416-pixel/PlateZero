
  // Auth check
  if (!localStorage.getItem("admin_id") || localStorage.getItem("admin_role") !== "admin") {
      window.location.href = "login.html";
  }

  // Populate Admin Name
  if(localStorage.getItem("admin_name")){
      document.getElementById('adminName').textContent = localStorage.getItem("admin_name");
  }

  function logoutAdmin() {
      localStorage.removeItem("admin_id");
      localStorage.removeItem("admin_name");
      localStorage.removeItem("admin_role");
      window.location.href = "login.html";
  }

  // Live clock
  function updateTime() {
    const now = new Date();
    document.getElementById('nowTime').textContent = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  updateTime();
  setInterval(updateTime, 1000);

  // Bar chart data
  let chartData = {
    breakfast: [0, 0, 0, 0, 0, 0, 0],
    lunch: [0, 0, 0, 0, 0, 0, 0],
    dinner: [0, 0, 0, 0, 0, 0, 0]
  };
  const maxVal = 450;
  let currentMeal = 'breakfast';
  let adminData = null;

  async function loadDashboardData() {
    try {
      let res = await fetch("http://127.0.0.1:8000/api/admin/dashboard_data");
      let data = await res.json();
      adminData = data;
      
      // KPIs
      document.getElementById('attendCount').innerText = data.kpis.attendance;
      document.getElementById('wasteReduced').innerText = data.kpis.waste_reduced;
      document.getElementById('savingsCount').innerText = data.kpis.savings;
      document.getElementById('wasteCount').innerText = data.kpis.high_waste_alerts;
      
      // Chart
      chartData = data.chartData;
      renderBars(currentMeal);
      
      // Alerts
      renderAlerts(data.alerts);
      
      // Donut
      renderDonut(data.wasteDistribution);
      
    } catch (e) {
      console.error("Error loading dashboard data:", e);
      showToast("❌ Error connecting to server");
    }
  }

  function renderBars(meal) {
    const data = chartData[meal] || [0, 0, 0, 0, 0, 0, 0];
    const container = document.getElementById('barChart');
    container.innerHTML = data.map((v, i) => {
      const pct = Math.min(Math.round((v / maxVal) * 100), 100);
      const color = i === 6 ? 'green' : (v < 280 ? 'red' : 'green');
      return `<div class="bar-col">
        <div class="bar-val">${v}</div>
        <div class="bar-wrap">
          <div class="bar-fill ${color}" data-h="${pct}" style="height:0%"></div>
        </div>
      </div>`;
    }).join('');
    // Animate after paint
    setTimeout(() => {
      document.querySelectorAll('.bar-fill').forEach(el => {
        el.style.height = el.dataset.h + '%';
      });
    }, 80);
  }

  function renderAlerts(alerts) {
      const container = document.getElementById("alertsContainer");
      if (!alerts || alerts.length === 0) {
          container.innerHTML = `<div style="font-size:0.8rem;color:var(--text3);text-align:center;padding:20px;">No new alerts</div>`;
          return;
      }
      
      container.innerHTML = alerts.map(a => `
          <div class="alert-item ${a.type}" onclick="dismissAlert(this, ${a.id})">
            <div class="alert-icon">${a.icon}</div>
            <div>
              <div class="alert-title">${a.title}</div>
              <div class="alert-desc">${a.desc}</div>
            </div>
            <div class="alert-time">${a.time}</div>
          </div>
      `).join("");
  }
  
  function renderDonut(wd) {
      const container = document.getElementById("donutWrap");
      const circum = 2 * Math.PI * 38; // 238.76
      
      let dashoffset = 0;
      let circlesHTML = '';
      let legendsHTML = '';
      
      wd.categories.forEach(cat => {
          const dashLen = (cat.percentage / 100) * circum;
          const gapLen = circum - dashLen;
          
          circlesHTML += `<circle cx="50" cy="50" r="38" fill="none" stroke="${cat.stroke}" stroke-width="14"
              stroke-dasharray="${dashLen} ${gapLen}" stroke-dashoffset="${-dashoffset}" transform="rotate(-90 50 50)"/>`;
              
          dashoffset += dashLen;
          
          legendsHTML += `
            <div class="donut-leg">
              <div class="donut-dot" style="background:${cat.color};"></div>
              <div class="donut-leg-name">${cat.name}</div>
              <div class="donut-leg-val" style="color:${cat.color};">${cat.percentage}%</div>
            </div>`;
      });
      
      container.innerHTML = `
          <svg class="donut-svg" width="100" height="100" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="38" fill="none" stroke="var(--bg)" stroke-width="14"/>
            ${circlesHTML}
            <text x="50" y="46" text-anchor="middle" fill="var(--text)" font-size="10" font-family="Syne" font-weight="800">${wd.total}</text>
            <text x="50" y="57" text-anchor="middle" fill="var(--text3)" font-size="6.5" font-family="DM Sans">${wd.unit}</text>
          </svg>
          <div class="donut-legends">
            ${legendsHTML}
          </div>
      `;
  }
  
  function exportCSV() {
      if (!adminData) return showToast("⚠️ Data not loaded yet");
      
      let csvContent = "data:text/csv;charset=utf-8,Day,Breakfast,Lunch,Dinner\\n";
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Today"];
      
      for (let i = 0; i < 7; i++) {
          let b = adminData.chartData.breakfast[i];
          let l = adminData.chartData.lunch[i];
          let d = adminData.chartData.dinner[i];
          csvContent += `${days[i]},${b},${l},${d}\\n`;
      }
      
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", "meal_analysis.csv");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast('📊 Exported to CSV');
  }
  
  function exportPDF() {
      window.print();
  }

  function setMealTab(el, meal) {
    document.querySelectorAll('.meal-tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    currentMeal = meal;
    renderBars(meal);
  }

  // Sanitation AI Upload name update
  function showFileName() {
    const input = document.getElementById('aiImageInput');
    if(input.files.length > 0) {
      document.getElementById('aiFileName').textContent = input.files[0].name;
    } else {
      document.getElementById('aiFileName').textContent = '';
    }
  }

  // Sanitation AI logic
  async function analyzePhoto(event) {
      if (event) event.preventDefault();

      let fileInput = document.getElementById("aiImageInput");
      if (!fileInput.files.length) {
          showToast("⚠️ Please select an image first!");
          return;
      }

      document.getElementById("aiResult").style.display = "block";
      document.getElementById("aiDetected").innerText = "Analyzing...";
      document.getElementById("aiConfidence").innerText = "...";
      document.getElementById("aiAction").innerText = "Please wait...";

      let formData = new FormData();
      formData.append("file", fileInput.files[0]);

      try {
          let res = await fetch("http://127.0.0.1:8000/analyze_sanitation", {
              method: "POST",
              body: formData
          });
          let data = await res.json();

          if (data.error) {
              document.getElementById("aiDetected").innerText = "Error: " + data.error;
              document.getElementById("aiAction").innerText = "Is the model trained?";
          } else {
              document.getElementById("aiDetected").innerText = data.prediction.replace(/_/g, " ").toUpperCase();
              document.getElementById("aiConfidence").innerText = data.confidence;
              document.getElementById("aiAction").innerText = data.recommendation;
              showToast("✅ Image analyzed successfully!");
          }
      } catch (e) {
          document.getElementById("aiDetected").innerText = "Network Error";
          document.getElementById("aiAction").innerText = "Failed to connect to backend.";
      }
  }

  // QR Generator & Attendance Logic
  let mealID = null;
  let qr = null;
  
  async function generateQR() {
    let meal = document.getElementById("mealSelect").value;
    const box = document.getElementById('qrBox');
    box.innerHTML = '<div style="color:var(--text3);font-size:1rem;margin:auto;">⏳ Generating...</div>';
    box.classList.remove('active');

    try {
      let res = await fetch(`http://127.0.0.1:8000/generate_qr/${meal}`);
      let data = await res.json();

      mealID = data.meal_id;
      document.getElementById("mealIdDisplay").innerText = "Session ID: " + mealID;
      
      box.innerHTML = "";
      box.classList.add('active');
      qr = new QRCode(box, {
          text: data.qr_data,
          width: 220,
          height: 220,
          colorDark: "#000000",
          colorLight: "#1db954"
      });

      showToast(`✅ QR generated for ${meal}`);
    } catch(e) {
      box.innerHTML = '🔲';
      showToast(`❌ Error generating QR`);
    }
  }

  async function updateAttendance() {
      if (!mealID) return;
      try {
          let res = await fetch(`http://127.0.0.1:8000/attendance/${mealID}`);
          let data = await res.json();
          document.getElementById("attendCount").innerText = data.attendance;
      } catch (e) {
          console.log("Polling error");
      }
  }
  
  // Continuously poll for live attendance
  setInterval(updateAttendance, 2000);

  // Alerts
  async function dismissAlert(el, alertId) {
    if (alertId) {
        try {
            await fetch(`http://127.0.0.1:8000/api/admin/alerts/${alertId}`, { method: "DELETE" });
        } catch(e) {
            console.error(e);
        }
    }
    el.style.opacity = '0';
    el.style.transform = 'translateX(20px)';
    el.style.transition = 'all 0.3s';
    setTimeout(() => el.remove(), 300);
    showToast('🗑️ Alert dismissed');
  }

  async function dismissAll() {
    // Optionally alert the backend that all alerts were dismissed
    document.querySelectorAll('.alert-item').forEach((el, i) => {
      setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(20px)';
        el.style.transition = 'all 0.3s';
        setTimeout(() => el.remove(), 300);
      }, i * 100);
    });
    showToast('✅ All alerts cleared');
  }

  // Nav
  function setNav(el) {
    document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
    el.classList.add('active');
  }

  // Toast
  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(() => t.classList.remove('show'), 2500);
  }

  // Init
  document.addEventListener('DOMContentLoaded', () => {
    loadDashboardData();
  });
