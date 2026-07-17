function plotlyLayoutBase() {
    return {
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#94A3B8" },
        margin: { t: 20, l: 50, r: 20, b: 40 },
        xaxis: { gridcolor: "#263A5B" },
        yaxis: { gridcolor: "#263A5B" },
    };
}

function loadMarketHistory(symbol) {
    fetch(`/api/market-history?symbol=${encodeURIComponent(symbol)}&days=30`)
        .then(r => r.json())
        .then(data => {
            Plotly.newPlot("chart-market-history", [
                {
                    x: data.dates,
                    y: data.prices,
                    type: "scatter",
                    mode: "lines",
                    fill: "tozeroy",
                    line: { color: "#00E5A8", width: 2 }
                }
            ], plotlyLayoutBase(), { responsive: true, displayModeBar: false });
        })
        .catch(err => console.error("Market history error:", err));
}

document.querySelectorAll("#symbol-tabs .region-tab").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll("#symbol-tabs .region-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        loadMarketHistory(btn.dataset.symbol);
    });
});

loadMarketHistory("BZ=F");
