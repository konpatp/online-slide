/* Native Plotly figures inside recipe-owned regions. Scientific data never changes. */
(function (global) {
  "use strict";
  global.renderScientificChartPanels = function (canvas, slide, api) {
    if (slide.data.views) {
      var storageKey = "online-slide.chart-views."+slide.id;
      var selection = Object.assign({}, slide.data.views[0].selection);
      try { Object.assign(selection, JSON.parse(localStorage.getItem(storageKey)||"{}")); } catch (_) {}
      var controls = document.createElement("div"); controls.className = "native-chart-controls gallery-controls";
      canvas.appendChild(controls);
      function renderView() {
        var view = slide.data.views.find(function (candidate) {
          return slide.data.selectors.every(function (selector) { return candidate.selection[selector.id] === selection[selector.id]; });
        }) || slide.data.views[0];
        selection = Object.assign({}, view.selection);
        canvas.querySelectorAll('.native-chart').forEach(function (chart) { if (chart._fullLayout) global.Plotly.purge(chart); });
        var old = canvas.querySelector('.native-charts'); if (old) old.remove();
        global.renderScientificFacetControls(controls,slide,slide.data.selectors,selection,function (key,value) {
          selection[key]=value;
          localStorage.setItem(storageKey,JSON.stringify(selection));
          renderView();
        });
        var resolved = Object.assign({}, slide, {data:Object.assign({},slide.data,view)});
        delete resolved.data.views; delete resolved.data.selectors;
        global.renderScientificChartPanels(canvas,resolved,api);
        canvas.querySelector('.native-charts').classList.add('with-facets');
      }
      renderView();
      return;
    }
    var body = document.createElement("div");
    body.className = "recipe-body native-charts";
    if (slide.data.legend || slide.data.decoders) {
      var legend = document.createElement("div"); legend.className = "plot-legend native-shared-legend";
      (slide.data.legend || []).forEach(function (item) {
        var entry = document.createElement("div"); entry.className = "legend-item";
        var swatch = document.createElement("span"); swatch.className = "legend-swatch";
        swatch.style.setProperty("--series", item.color);
        entry.append(swatch, api.editableText(slide, item.label, "span", "legend-label"));
        legend.appendChild(entry);
      });
      (slide.data.decoders || []).forEach(function (label) {
        legend.appendChild(api.editableText(slide,label,"span","legend-label"));
      });
      body.appendChild(legend);
      body.classList.add("with-shared-legend");
    }
    if (slide.data.yLabel) body.appendChild(api.editableText(slide, slide.data.yLabel, "div", "native-shared-y"));
    var panels = document.createElement("div");
    panels.className = "native-chart-panels";
    panels.style.gridTemplateColumns = "repeat(" + slide.data.panels.length + ",minmax(0,1fr))";
    slide.data.panels.forEach(function (panel) {
      var column = document.createElement("section");
      column.className = "native-chart-column";
      if (panel.heading) column.appendChild(api.editableText(slide, panel.heading, "h2", "native-panel-heading"));
      if (panel.subheading) column.appendChild(api.editableText(slide,panel.subheading,"div","native-panel-subheading"));
      var chart = document.createElement("div");
      chart.className = "native-chart";
      chart.dataset.chartId = panel.chart;
      if(api.effectiveComponent(slide,panel.chart).hidden) {
        chart.classList.add('curator-hidden-component');
        chart.dataset.chartReady='true';
      }
      chart.setAttribute("aria-label", panel.heading ? api.effectiveComponent(slide, panel.heading).text : "Scientific evidence plot");
      column.appendChild(chart);
      if (panel.caption) column.appendChild(api.editableText(slide, panel.caption, "div", "native-panel-caption"));
      if(panel.endpoints) {
        var strip=document.createElement('div');strip.className='native-endpoint-strip';
        panel.endpoints.forEach(function(endpoint){
          var item=document.createElement('div');item.className='native-endpoint';
          ['label','value','horizon'].forEach(function(key){item.appendChild(api.editableText(slide,endpoint[key],'span','native-endpoint-'+key));});
          strip.appendChild(item);
        });
        column.appendChild(strip);
      }
      panels.appendChild(column);
      requestAnimationFrame(function () {
        if (!chart.isConnected) return;
        var component = api.effectiveComponent(slide, panel.chart);
        if(component.hidden && !api.isEditMode()) return;
        var figure = JSON.parse(JSON.stringify(component.figure));
        var layout = figure.layout;
        var edits = component.chartLayout || {};
        layout.legend = Object.assign({}, layout.legend, edits.legend || {});
        (layout.annotations || []).forEach(function (item) {
          Object.assign(item, (edits.annotations || {})[item.name] || {});
        });
        layout.width = chart.clientWidth;
        layout.height = chart.clientHeight;
        layout.autosize = false;
        layout.paper_bgcolor = "white";
        layout.plot_bgcolor = "white";
        layout.font = Object.assign({family:"Inter, sans-serif",size:36,color:"#14233b"}, layout.font);
        ["xaxis", "yaxis"].forEach(function (key) {
          var axis = layout[key] || {};
          axis.automargin = true;
          axis.tickfont = Object.assign({}, axis.tickfont, {size:Math.max(36, (axis.tickfont || {}).size || 0)});
          if (axis.title && axis.title.text) {
            axis.title.font = Object.assign({}, axis.title.font, {size:38});
            axis.title.standoff = 18;
          }
          layout[key] = axis;
        });
        figure.data.forEach(function (trace) {
          if (trace.text) trace.textfont = Object.assign({}, trace.textfont, {size:38});
        });
        layout.uirevision = slide.id + ":" + panel.chart;
        var editable = api.isEditMode();
        global.Plotly.newPlot(chart, figure.data, layout, {
          responsive:false, displaylogo:false, scrollZoom:false,
          toImageButtonOptions:{format:"svg"},
          edits:{annotationPosition:editable,annotationText:editable,legendPosition:editable},
          showTips:false
        }).then(function () {
          if (!chart.isConnected) { global.Plotly.purge(chart); return; }
          chart.dataset.chartReady = "true";
          chart.on("plotly_relayout", function (changes) {
            if (!api.isEditMode()) return;
            var next = JSON.parse(JSON.stringify(api.effectiveComponent(slide, panel.chart).chartLayout || {}));
            var changed = false;
            Object.keys(changes).forEach(function (key) {
              if (/^legend\.[xy]$/.test(key)) {
                next.legend = next.legend || {};
                next.legend[key.split(".")[1]] = changes[key];
                changed = true;
              }
              var match = key.match(/^annotations\[(\d+)\]\.(x|y|ax|ay|text)$/);
              if (!match) return;
              var annotation = layout.annotations[Number(match[1])];
              if (!annotation || !annotation.name) return;
              next.annotations = next.annotations || {};
              next.annotations[annotation.name] = next.annotations[annotation.name] || {};
              next.annotations[annotation.name][match[2]] = changes[key];
              changed = true;
            });
            if (changed && JSON.stringify(next) !== JSON.stringify(component.chartLayout || {})) {
              api.saveChartLayout(slide.id, panel.chart, next);
            }
          });
        }).catch(function (error) {
          chart.dataset.chartError = error.message;
          chart.textContent = "Chart failed: " + error.message;
        });
      });
    });
    body.appendChild(panels);
    if (slide.data.xLabel) body.appendChild(api.editableText(slide, slide.data.xLabel, "div", "native-shared-x"));
    canvas.appendChild(body);
  };
}(window));
