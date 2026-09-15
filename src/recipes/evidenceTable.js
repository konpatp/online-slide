// Recipe owns layout; injected editor capabilities own mutable state.
import {HEAT_COLORS,numericCell,heatDomain,heatColor} from './tableHeatmap';
export function createEvidenceTable(api) {
const global = window;
const {editableText,effectiveComponent,effectiveTable,startTableColumnResize,fitGroupInRegion} = api;
function evidenceTable(canvas, slide) {
  if(slide.data.tables) {
    var collection=document.createElement('div');
    collection.className='recipe-body table-panels-body';
    var selector=slide.data.tableSelector;
    if(selector) collection.classList.add('selectable-tables');
    var storageKey='online-slide.table-view.'+slide.id;
    var active=slide.data.initialTable || slide.data.tables[0].id;
    if(selector) {
      try { active=localStorage.getItem(storageKey) || active; } catch (_) {}
      if(!slide.data.tables.some(function(table){return table.id===active;})) active=slide.data.tables[0].id;
    }
    function renderTables() {
      collection.textContent='';
      var sharedHeat=slide.data.heatmap;
      if(sharedHeat && !sharedHeat.domain) {
        var values=function(editedId,editedText) { return slide.data.tables.flatMap(function(data) {
          var context=Object.assign({},slide,{data:data,_tableKey:slide.id+'::table::'+data.id});
          return effectiveTable(context).rows.flatMap(row=>row.cells.map(id=>numericCell(id===editedId?editedText:effectiveComponent(context,id).text)));
        }); };
        sharedHeat=Object.assign({},sharedHeat,{values:values});
      }
      if(selector) {
        var controls=document.createElement('div');
        global.renderScientificFacetControls(controls,slide,[Object.assign({id:'table'},selector)],{table:active},function(_,value){
          active=value;
          try {localStorage.setItem(storageKey,value);} catch (_) {}
          renderTables();
        });
        collection.appendChild(controls);
      }
      slide.data.tables.filter(function(table){return !selector || table.id===active;}).forEach(function(data) {
      if(data.heading) collection.appendChild(editableText(slide,data.heading,'div','table-panel-heading'));
      if(data.visibility) collection.appendChild(editableText(slide,data.visibility,'div','table-panel-control'));
      evidenceTable(collection,Object.assign({},slide,{data:Object.assign({},data,{heatmap:data.heatmap || sharedHeat}),_tableKey:slide.id+'::table::'+data.id}));
      });
    }
    canvas.appendChild(collection);
    renderTables();
    return;
  }
  var model = effectiveTable(slide);
  var heat=slide.data.heatmap;
  function resolveDomain(editedId,editedText) {
    return heat && (heat.domain || heatDomain(heat.values ? heat.values(editedId,editedText) :
      model.rows.flatMap(row=>row.cells.map(id=>numericCell(id===editedId?editedText:effectiveComponent(slide,id).text)))));
  }
  var domain=resolveDomain();
  var body = document.createElement("div");
  body.className = "recipe-body table-body";
  if(slide.data.visibility && effectiveComponent(slide,slide.data.visibility).hidden) body.classList.add('curator-hidden-component');
  body.setAttribute('data-table-panel-id',slide.data.id || 'main');
  if(heat) {
    body.classList.add('heatmap-table-body');
    var legend=document.createElement('div');
    legend.className='table-heatmap-legend';
    legend.appendChild(editableText(slide,heat.label,'span','table-heatmap-label'));
    var low=document.createElement('span');legend.appendChild(low);
    var ramp=document.createElement('span');ramp.className='table-heatmap-ramp';
    ramp.style.background='linear-gradient(90deg, '+HEAT_COLORS.join(', ')+')';
    ramp.setAttribute('aria-hidden','true');legend.appendChild(ramp);
    var high=document.createElement('span');legend.appendChild(high);
    body.appendChild(legend);
  }
  var table = document.createElement("table");
  table.className = "evidence-table";
  table.setAttribute("data-native-table", slide._tableKey || slide.id);
  var colgroup = document.createElement("colgroup");
  var totalWidth = model.columns.reduce(function (sum, column) { return sum + column.width; }, 0);
  model.columns.forEach(function (column) {
    var col = document.createElement("col");
    col.setAttribute("data-table-column-id", column.id);
    col.style.width = (column.width / totalWidth * 100).toFixed(3) + "%";
    colgroup.appendChild(col);
  });
  table.appendChild(colgroup);
  var head = document.createElement("thead");
  var headRow = document.createElement("tr");
  model.columns.forEach(function (column, columnIndex) {
    var th = document.createElement("th");
    th.setAttribute("data-table-cell", "header:" + column.id);
    th.setAttribute("data-table-row-id", "table-header");
    th.setAttribute("data-table-row-index", "-1");
    th.setAttribute("data-table-column-id", column.id);
    th.setAttribute("data-table-column-index", String(columnIndex));
    th.appendChild(editableText(slide, column.label, "div", "table-heading"));
    var resizer = document.createElement("button");
    resizer.type = "button";
    resizer.className = "table-column-resizer";
    resizer.setAttribute("aria-label", "Resize " + effectiveComponent(slide, column.label).text + " column");
    resizer.addEventListener("pointerdown", function (event) {
      startTableColumnResize(slide, column.id, event);
    });
    th.appendChild(resizer);
    headRow.appendChild(th);
  });
  head.appendChild(headRow);
  table.appendChild(head);
  var tbody = document.createElement("tbody");
  model.rows.forEach(function (row, rowIndex) {
    var tr = document.createElement("tr");
    tr.setAttribute("data-table-row", row.id);
    var label = document.createElement("th");
    label.scope = "row";
    label.setAttribute("data-table-cell", row.id + ":" + model.columns[0].id);
    label.setAttribute("data-table-row-id", row.id);
    label.setAttribute("data-table-row-index", String(rowIndex));
    label.setAttribute("data-table-column-id", model.columns[0].id);
    label.setAttribute("data-table-column-index", "0");
    label.appendChild(editableText(slide, row.label, "div", "table-row-label"));
    tr.appendChild(label);
    row.cells.forEach(function (componentId, index) {
      var td = document.createElement("td");
      var column = model.columns[index + 1];
      td.setAttribute("data-table-cell", row.id + ":" + column.id);
      td.setAttribute("data-table-row-id", row.id);
      td.setAttribute("data-table-row-index", String(rowIndex));
      td.setAttribute("data-table-column-id", column.id);
      td.setAttribute("data-table-column-index", String(index + 1));
      if (componentId === row.best) td.classList.add("row-best");
      if (componentId === row.globalBest) td.classList.add("global-best");
      var content=editableText(slide, componentId, "div", "table-value");
      td.appendChild(content);
      if(heat) {
        td.classList.add('heatmap-cell');
        td._paintHeat=function() {
          var style=heatColor(numericCell(content.textContent),domain);
          td.style.backgroundColor=style?style.background:'';
          td.style.color=style?style.foreground:'';
          td.dataset.heatmapValue=style?String(style.value):'';
        };
        content.addEventListener('input',function() {
          canvas.querySelectorAll('.heatmap-table-body').forEach(function(panel) {
            panel._refreshHeat(componentId,content.textContent);
          });
        });
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  body.appendChild(table);
  canvas.appendChild(body);
  if(heat) {
    body._refreshHeat=function(editedId,editedText) {
      domain=resolveDomain(editedId,editedText);
      low.textContent=domain?String(domain[0]):'—';
      high.textContent=domain?String(domain[1]):'—';
      legend.dataset.heatmapDomain=JSON.stringify(domain);
      body.querySelectorAll('.heatmap-cell').forEach(function(cell){cell._paintHeat();});
    };
    body._refreshHeat();
  }
  fitGroupInRegion(table, body, {
    mode: "evidence-table-region",
    property: "--table-fit-scale",
    minScale: 0.58,
    maxScale: 1,
    contentSelector: ".table-heading, .table-row-label, .table-value"
  });
}


return evidenceTable;
}
