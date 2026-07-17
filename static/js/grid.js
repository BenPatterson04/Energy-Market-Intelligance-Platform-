fetch("/api/grid-generation-mix")
    .then(r => r.json())
    .then(data => {

        Plotly.newPlot("chart-generation-mix", [
            {
                x: data.map(d => d.fuel),
                y: data.map(d => d.percent),
                type: "bar",
                marker: { color: "#00E5A8" }
            }
        ], {
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#94A3B8" },
            margin: { t: 20, l: 50, r: 20, b: 80 },
            xaxis: { gridcolor: "#263A5B", tickangle: -30 },
            yaxis: { gridcolor: "#263A5B", title: "% of generation" },
        }, { responsive: true, displayModeBar: false });

    })
    .catch(err => console.error("Generation mix error:", err));
