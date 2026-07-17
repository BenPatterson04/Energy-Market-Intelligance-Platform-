// ======================================
// GridWise v4 - i-SEM Page Interactions
// ======================================

let currentRegion = "ALL";

function plotlyLayoutBase(title) {
    return {
        title: { text: title, font: { color: "#F8FAFC", size: 14 } },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#94A3B8" },
        margin: { t: 30, l: 50, r: 20, b: 40 },
        xaxis: { gridcolor: "#263A5B" },
        yaxis: { gridcolor: "#263A5B" },
        legend: { orientation: "h", y: -0.2 }
    };
}

function loadHistoryCharts(region) {

    fetch(`/api/isem-history?region=${region}&hours=24`)
        .then(r => r.json())
        .then(data => {

            Plotly.newPlot("chart-demand-wind", [
                {
                    x: data.timestamps, y: data.demand_mw,
                    name: "Demand (MW)", type: "scatter", mode: "lines",
                    line: { color: "#00E5A8", width: 2 }
                },
                {
                    x: data.timestamps, y: data.wind_mw,
                    name: "Wind (MW)", type: "scatter", mode: "lines",
                    line: { color: "#4EA3FF", width: 2 }
                }
            ], plotlyLayoutBase(""), { responsive: true, displayModeBar: false });

            Plotly.newPlot("chart-co2", [
                {
                    x: data.timestamps, y: data.co2_intensity,
                    name: "gCO₂/kWh", type: "scatter", mode: "lines",
                    fill: "tozeroy", line: { color: "#FF5B6B", width: 2 }
                }
            ], plotlyLayoutBase(""), { responsive: true, displayModeBar: false });

        })
        .catch(err => console.error("History chart error:", err));
}

function loadGridMap() {

    fetch("/api/grid-map")
        .then(r => r.json())
        .then(nodes => {

            const interconnectors = nodes.filter(n => n.type === "interconnector");
            const demandCentres = nodes.filter(n => n.type === "demand");

            const trace = (arr, color) => ({
                type: "scattergeo",
                lon: arr.map(n => n.lon),
                lat: arr.map(n => n.lat),
                text: arr.map(n => n.name),
                mode: "markers",
                marker: { size: 12, color: color, line: { width: 1, color: "#0B1626" } }
            });

            Plotly.newPlot("grid-map", [
                trace(interconnectors, "#4EA3FF"),
                trace(demandCentres, "#00E5A8")
            ], {
                geo: {
                    scope: "europe",
                    center: { lat: 53.4, lon: -7.5 },
                    projection: { scale: 9 },
                    showland: true,
                    landcolor: "#16263F",
                    countrycolor: "#263A5B",
                    bgcolor: "transparent"
                },
                paper_bgcolor: "transparent",
                margin: { t: 10, l: 0, r: 0, b: 0 },
                showlegend: false
            }, { responsive: true, displayModeBar: false });

        })
        .catch(err => console.error("Grid map error:", err));
}

function loadCommentary(audience) {

    const box = document.getElementById("commentary-box");
    box.innerHTML = '<p class="commentary-loading">Generating today\'s briefing…</p>';

    fetch(`/api/commentary?audience=${audience}`)
        .then(r => r.json())
        .then(data => {
            box.innerHTML = `<p>${data.commentary}</p>`;
        })
        .catch(() => {
            box.innerHTML = '<p class="commentary-loading">Commentary unavailable right now.</p>';
        });
}

function addWatchlistItem() {

    const select = document.getElementById("watchlist-metric");
    const option = select.options[select.selectedIndex];

    fetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            item_key: option.value,
            label: option.dataset.label,
            category: option.dataset.category
        })
    }).then(() => window.location.reload());
}

function removeWatchlistItem(itemKey) {
    fetch("/api/watchlist", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_key: itemKey })
    }).then(() => window.location.reload());
}

function addAlert() {

    const metric = document.getElementById("alert-metric").value;
    const condition = document.getElementById("alert-condition").value;
    const threshold = document.getElementById("alert-threshold").value;

    if (!threshold) return;

    fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            metric: metric,
            label: document.getElementById("alert-metric").selectedOptions[0].text,
            condition: condition,
            threshold: threshold
        })
    }).then(() => window.location.reload());
}

function removeAlert(alertId) {
    fetch(`/api/alerts/${alertId}`, { method: "DELETE" })
        .then(() => window.location.reload());
}

// ---- Region tab switching ----

document.querySelectorAll("#region-tabs .region-tab").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll("#region-tabs .region-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentRegion = btn.dataset.region;
        loadHistoryCharts(currentRegion);
    });
});

// ---- Commentary tab switching ----

document.querySelectorAll(".commentary-tabs .region-tab").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".commentary-tabs .region-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        loadCommentary(btn.dataset.audience);
    });
});

// ---- Init ----

loadHistoryCharts(currentRegion);
loadGridMap();
loadCommentary("domestic");
