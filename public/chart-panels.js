/* Native Plotly figures inside recipe-owned regions. Scientific data never changes. */
(function (global) {
  "use strict";
  // Plotly uses uid in unescaped cleanup selectors. Encode, never slugify:
  // distinct authored identities must remain distinct (including Unicode).
  function runtimeTraceId(value) {
    var text=String(value), result='trace';
    for(var i=0;i<text.length;i++)result+='_'+text.charCodeAt(i).toString(16).padStart(4,'0');
    return result;
  }
  global.scientificRuntimeTraceId=runtimeTraceId;
  // Keep only lightweight presenter view state, not detached plots or data.
  var chartViews=new Map();
  global.disposeScientificChart=function(chart) {
    if(chart.dataset.chartReady==='true' && chart.rememberView)chart.rememberView();
    if(global.Plotly && chart._fullLayout)global.Plotly.purge(chart);
  };
  // Centered x-distance window, matching the retained chart interaction.
  // Sorting is stable; radius zero returns the exact authored observations.
  function centeredMeanByX(xs,ys,radius) {
    if(!Array.isArray(xs)||!Array.isArray(ys)||xs.length!==ys.length) throw new Error('Smoothing needs equal-length arrays');
    if(!radius)return {x:xs.slice(),y:ys.slice()};
    var points=xs.map(function(x,i){if(!Number.isFinite(Number(x)))throw new Error('Smoothing needs numeric x');return {x:Number(x),y:ys[i],i:i};});
    points.sort(function(a,b){return a.x-b.x || a.i-b.i;});
    var left=0,right=0,sum=0,count=0;
    return {x:points.map(function(p){return p.x;}),y:points.map(function(p){
      while(right<points.length && points[right].x<=p.x+radius){var v=Number(points[right++].y);if(Number.isFinite(v)){sum+=v;count++;}}
      while(left<points.length && points[left].x<p.x-radius){var v=Number(points[left++].y);if(Number.isFinite(v)){sum-=v;count--;}}
      return count?sum/count:p.y;
    })};
  }
  global.scientificCenteredMeanByX=centeredMeanByX;
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
        canvas.querySelectorAll('.native-chart').forEach(global.disposeScientificChart);
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
    var smoothing=slide.data.smoothing, radius=smoothing?smoothing.radius:0;
    var smoothingKey='online-slide.chart-smoothing.'+slide.id;
    if(smoothing){
      var saved=Number(localStorage.getItem(smoothingKey));
      if(localStorage.getItem(smoothingKey)!==null && Number.isFinite(saved) && saved>=0 && saved<=smoothing.max)radius=saved;
    }
    if (slide.data.legend || slide.data.decoders || smoothing) {
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
      if(smoothing){
        var control=document.createElement('label');control.className='native-smoothing';
        var input=document.createElement('input');input.type='range';input.min=0;input.max=smoothing.max;input.step=smoothing.step;input.value=radius;
        input.setAttribute('aria-label','Centered smoothing radius');
        var output=document.createElement('output');
        function updateCaption(){output.textContent='centered ±'+radius+' '+smoothing.unit;}
        updateCaption();control.append(input,output);legend.appendChild(control);
        var timer;
        input.addEventListener('input',function(){
          radius=Number(input.value);localStorage.setItem(smoothingKey,String(radius));updateCaption();clearTimeout(timer);
          timer=setTimeout(function(){
            if(!body.isConnected)return;
            body.querySelectorAll('.native-chart[data-chart-ready="true"]').forEach(function(chart){
              var source=api.effectiveComponent(slide,chart.dataset.chartId).figure.data;
              var indices=[],xs=[],ys=[];
              source.forEach(function(trace,index){if(String(trace.mode||'').indexOf('lines')<0)return;
                var values=centeredMeanByX(trace.x,trace.y,radius);indices.push(index);xs.push(values.x);ys.push(values.y);
              });
              if(indices.length)global.Plotly.restyle(chart,{x:xs,y:ys},indices);
            });
          },80);
        });
      }
      body.appendChild(legend);
      body.classList.add("with-shared-legend");
    }
    if (slide.data.yLabel) body.appendChild(api.editableText(slide, slide.data.yLabel, "div", "native-shared-y"));
    var panels = document.createElement("div");
    panels.className = "native-chart-panels";
    panels.style.gridTemplateColumns = "repeat(" + slide.data.panels.length + ",minmax(0,1fr))";
    if(slide.data.layout==='main-with-diagnostics'){
      panels.classList.add('main-with-diagnostics');
      panels.style.gridTemplateColumns='minmax(0,1.8fr) minmax(0,1fr)';
    }
    slide.data.panels.forEach(function (panel, panelIndex) {
      var column = document.createElement("section");
      column.className = "native-chart-column";
      if (panel.heading) column.appendChild(api.editableText(slide, panel.heading, "h2", "native-panel-heading"));
      if (panel.subheading) column.appendChild(api.editableText(slide,panel.subheading,"div","native-panel-subheading"));
      var chart = document.createElement("div");
      chart.className = "native-chart";
      chart.dataset.chartId = panel.chart;
      api.bindTextRegion(slide,panel.chart,chart,chart,{});
      chart.addEventListener('click',function(event) {
        if(!api.isEditMode())return;
        var box=chart.getBoundingClientRect(),edge=Math.min(event.clientX-box.left,box.right-event.clientX,event.clientY-box.top,box.bottom-event.clientY);
        if(edge<=12) {event.stopPropagation();api.selectBoundedComponent(slide.id,panel.chart,chart);}
      });
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
        var viewKey=JSON.stringify([slide.id,panel.chart]);
        var sourceSignature=api.sourceRevision(slide.id);
        var savedView=chartViews.get(viewKey);
        if(savedView && savedView.source!==sourceSignature)savedView=null;
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
        // Endpoint labels outside paper coordinates need their own gutter.
        // Plotly does not include annotation ink in axis automargins.
        (layout.annotations || []).forEach(function(annotation) {
          if(annotation.xref!=='paper' || annotation.x<1 || annotation.xanchor!=='left')return;
          var measure=document.createElement('canvas').getContext('2d');
          var text=document.createElement('span');text.innerHTML=annotation.text || '';
          var font=Object.assign({},layout.font,annotation.font || {});
          measure.font='700 '+font.size+'px '+font.family;
          layout.margin=Object.assign({},layout.margin);
          layout.margin.r=Math.max(layout.margin.r || 0,Math.ceil(measure.measureText(text.textContent).width+40));
        });
        if (slide.data.layout==='main-with-diagnostics') {
          // One shared horizontal decoder and the authored metric headings
          // reserve the compact diagnostic panels for measured data.
          if(slide.data.xLabel && layout.xaxis) delete layout.xaxis.title;
          if(panel.heading && layout.yaxis) delete layout.yaxis.title;
          layout.margin=Object.assign({},layout.margin,{t:12,b:50,l:72,r:20});
          if(panelIndex>0 && layout.yaxis && !layout.yaxis.tickvals) {
            delete layout.yaxis.dtick;
            layout.yaxis.tickmode='auto';layout.yaxis.nticks=3;
          }
        }
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
          if(trace.uid!==undefined)trace.uid=runtimeTraceId(trace.uid);
          if(savedView && Object.prototype.hasOwnProperty.call(savedView.visible,trace.uid))
            trace.visible=savedView.visible[trace.uid];
          if (trace.text) trace.textfont = Object.assign({}, trace.textfont, {size:38});
          if(smoothing && String(trace.mode||'').indexOf('lines')>=0){
            var values=centeredMeanByX(trace.x,trace.y,radius);trace.x=values.x;trace.y=values.y;
          }
        });
        layout.uirevision = slide.id + ":" + panel.chart;
        if(savedView)Object.keys(savedView.axes).forEach(function(key){
          layout[key]=Object.assign({},layout[key],savedView.axes[key]);
        });
        var editable = api.isEditMode();
        global.Plotly.newPlot(chart, figure.data, layout, {
          responsive:false, displaylogo:false, scrollZoom:false,
          toImageButtonOptions:{format:"svg"},
          edits:{annotationPosition:editable,annotationText:editable,legendPosition:editable},
          showTips:false
        }).then(function () {
          if (!chart.isConnected) { global.Plotly.purge(chart); return; }
          chart.dataset.chartReady = "true";
          chart.rememberView=function() {
            var axes={},visible={};
            Object.keys(chart.layout).forEach(function(key){
              if(!/^[xy]axis\d*$/.test(key))return;
              var axis=chart.layout[key];
              axes[key]={autorange:axis.autorange};
              if(Array.isArray(axis.range))axes[key].range=axis.range.slice();
            });
            chart.data.forEach(function(trace){if(trace.uid!==undefined)visible[trace.uid]=trace.visible===undefined?true:trace.visible;});
            chartViews.delete(viewKey);
            chartViews.set(viewKey,{source:sourceSignature,axes:axes,visible:visible});
            if(chartViews.size>64)chartViews.delete(chartViews.keys().next().value);
          };
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
