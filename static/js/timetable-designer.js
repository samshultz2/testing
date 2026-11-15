var LAYOUTS = {
    saturday: {title:'Saturday Class Timetable', mode:'grid',
               fields:['week','group','time','dur','subject','teacher'],
               hint:'Each week becomes a row and each time slot a column, with the teacher shown under the subject. Set the “First Saturday” date above; the actual date for every week is worked out for you. Tick any Saturday as lesson-free and that week (and all later weeks) shift to the next Saturday. Use “Class / Stream” to stack more than one group under the same week (e.g. SSS3 and JSS3).'},
    holiday:  {title:'Holiday Lesson Timetable', mode:'grid',
               fields:['date','day','group','time','dur','subject','teacher'],
               hint:'Each day is a row and each time slot a column. Enter a Date and the Day fills in automatically (both show together in the day column). Use “Class / Stream” when a day has different subjects per group — e.g. on Monday, Science vs Arts/Social-Science get their own rows.'},
    exam:     {title:'Examination Timetable', mode:'list',
               fields:['date','time','dur','subject','venue','teacher'],
               hint:'Each exam is one row, listed by date and time. A blank “Invigilator’s Signature” column is added on the printout.'},
    list_table:{title:'Custom Table', mode:'list_table', fields:[],
               hint:'Set the column headers, then type into each auto-numbered row — for a staff list, a duty list, any table.'},
};
var FIELD = {
    week:   {label:'Week'},
    date:   {label:'Date'},
    day:    {label:'Day'},
    group:  {label:'Class / Stream (optional)'},
    time:   {label:'Start time'},
    dur:    {label:'Duration (minutes)'},
    subject:{label:'Subject'},
    teacher:{label:'Teacher (optional)'},
    venue:  {label:'Venue'},
};
var DAY_ORDER = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
var rows = [];   // each: {date,day,group,time,dur,subject,teacher,venue}

// Sweeping / duty rosters reuse the blank-grid renderer, but with roster presets and
// editable cells. The primary axis (rows) is weeks or days; columns are days/areas.
// A class's own sweeping roster: each time-unit (a whole week, or a single day) is
// assigned ONE group of students who sweep together for that whole period — so a
// single "Students on Duty" column, one fillable cell per week/day.
var ROSTER_PRESETS = {
    roster_week: {title:'Weekly Sweeping Roster',
                  rows:'Week 1\nWeek 2\nWeek 3\nWeek 4\nWeek 5\nWeek 6'},
    roster_day:  {title:'Daily Sweeping Roster',
                  rows:'Monday\nTuesday\nWednesday\nThursday\nFriday'},
};
// Roster columns are numbered name-boxes (one student per box), 1..N (max 10).
function rosterCols(){
    var n=Math.max(1, Math.min(10, parseInt(el('rosterCount').value,10)||5));
    var a=[]; for(var i=1;i<=n;i++) a.push(String(i));
    return a.join(', ');
}
var rosterCells = {};   // "rowIndex:colIndex" -> typed text (persists across re-renders)

function el(id){ return document.getElementById(id); }
function esc(s){ var d=document.createElement('div'); d.textContent=s==null?'':s; return d.innerHTML; }
function isRoster(){ return !!ROSTER_PRESETS[el('layout').value]; }
function isListTable(){ return el('layout').value==='list_table'; }
function isBlankGrid(){ var v=el('layout').value; return v==='grid' || v==='list_table' || isRoster(); }
function layout(){
    var v=el('layout').value;
    if(ROSTER_PRESETS[v]) return {title:ROSTER_PRESETS[v].title, mode:'grid', fields:[]};
    return LAYOUTS[v] || LAYOUTS.saturday;
}

function addMinutes(hhmm, mins){
    if(!hhmm) return '';
    var p=hhmm.split(':'); if(p.length<2) return hhmm;
    var d=new Date(2000,0,1,parseInt(p[0],10),parseInt(p[1],10));
    d.setMinutes(d.getMinutes()+(parseInt(mins,10)||0));
    return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);
}
function fmtT(hhmm){ if(!hhmm) return ''; var p=hhmm.split(':'); return p.length<2?hhmm:(parseInt(p[0],10)+':'+p[1]); }
// Flexible date parsing: ISO (YYYY-MM-DD) and D/M/YY or D/M/YYYY (also - or .).
function parseDateAny(s){
    s=(s||'').trim(); if(!s) return null;
    var y,m,d, a=s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if(a){ y=+a[1]; m=+a[2]; d=+a[3]; }
    else { var b=s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})$/);
        if(b){ d=+b[1]; m=+b[2]; y=+b[3]; if(y<100) y+=2000; } else return null; }
    var dt=new Date(y, m-1, d); if(isNaN(dt)) return null;
    return {iso:y+'-'+('0'+m).slice(-2)+'-'+('0'+d).slice(-2), dt:dt, y:y, m:m, d:d};
}
function toISO(s){ var p=parseDateAny(s); return p?p.iso:s; }
function dayFromDate(d){ var p=parseDateAny(d);
    return p?['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][p.dt.getDay()]:''; }
function fmtDate(d){ var p=parseDateAny(d); return p ? (p.d+'/'+p.m+'/'+String(p.y).slice(-2)) : (d||''); }
// 12-hour clock label, e.g. "9", "9:30", "12", with optional am/pm suffix.
function clock12(hhmm, suffix){
    var p=(hhmm||'').split(':'); if(p.length<2) return hhmm||'';
    var h=+p[0], m=+p[1], hh=h%12; if(hh===0) hh=12;
    var s=hh+(m?(':'+('0'+m).slice(-2)):'');
    return suffix ? s+(h<12?'am':'pm') : s;
}
function periodLabel(r){
    if(!r.time) return '';
    if(!r.dur) return clock12(r.time, true);
    var end=addMinutes(r.time, r.dur);
    var sh=+r.time.split(':')[0], eh=+end.split(':')[0];
    var diffMer=(sh<12)!==(eh<12);                 // show am/pm on start only if it differs from end
    return clock12(r.time, diffMer)+' – '+clock12(end, true);
}
function periodKey(r){ return r.time+'|'+(r.dur||''); }
function dayRank(d){ var i=DAY_ORDER.indexOf(d); return i<0?99:i; }
function isAll(g){ return (g||'').trim().toLowerCase()==='all'; }

// ---------- mobile-first session editor ----------
function fieldInput(r,c){
    var v=esc(r[c]||'');
    switch(c){
        case 'week':    return '<input type="number" min="1" step="1" inputmode="numeric" data-f="week" value="'+v+'" placeholder="e.g. 1">';
        case 'date':    return '<input type="date" data-f="date" value="'+v+'">';
        case 'day':     return '<input data-f="day" list="dayList" value="'+v+'" placeholder="e.g. Monday">';
        case 'time':    return '<input type="time" data-f="time" value="'+v+'">';
        case 'dur':     return '<input type="number" min="0" step="5" inputmode="numeric" data-f="dur" value="'+v+'" placeholder="60">';
        case 'subject': return '<input data-f="subject" list="subjectList" value="'+v+'" placeholder="e.g. Mathematics">';
        case 'teacher': return '<input data-f="teacher" value="'+v+'" placeholder="e.g. Mr Bello">';
        case 'group':   return '<input data-f="group" value="'+v+'" placeholder="e.g. Science / Arts / SSS3">';
        case 'venue':   return '<input data-f="venue" value="'+v+'" placeholder="Hall / Room">';
    }
    return '';
}
function sessCard(r,i){
    var inner=layout().fields.map(function(c){
        return '<label><span>'+FIELD[c].label+'</span>'+fieldInput(r,c)+'</label>';
    }).join('');
    return '<div class="sess-card" data-i="'+i+'">'
         + '<div class="sess-top"><strong>Session '+(i+1)+'</strong>'
         + '<span class="sess-actions">'
         + '<button type="button" class="sess-dup" data-call="dupRow" data-args="'+i+'"><i class="fas fa-copy"></i> Duplicate</button>'
         + '<button type="button" class="sess-del" data-call="delRow" data-args="'+i+'"><i class="fas fa-trash"></i> Remove</button>'
         + '</span></div>'
         + '<div class="sess-grid">'+inner+'</div></div>';
}
var BULK_SHORT={week:'Week',date:'Date',day:'Day',group:'Class/Stream',time:'Start',dur:'Minutes',subject:'Subject',teacher:'Teacher',venue:'Venue'};
var BULK_FIELD_HINT={
    week:'the week number, e.g. 1',
    date:'the date, e.g. 2025-09-15',
    day:'the day name, e.g. Monday',
    group:'the class/stream, or leave blank if not shown',
    time:'the start time, e.g. 9:00am or 09:00',
    dur:'the duration in minutes, e.g. 60',
    subject:'the subject or activity',
    teacher:'the teacher’s name, or leave blank',
    venue:'the venue/room',
};
var BULK_INTRO={
    saturday:'Read this Saturday class schedule',
    holiday:'Read this holiday lesson schedule',
    exam:'Read this exam timetable',
};
function buildBulkPrompt(){
    var fields = layout().fields;
    if(!fields.length) return '';
    var numbered = fields.map(function(f,i){ return (i+1)+'. '+BULK_SHORT[f]+' — '+BULK_FIELD_HINT[f]; }).join('\n');
    return (BULK_INTRO[el('layout').value] || 'Read this list of sessions')
        + ' (photo, screenshot or rough notes) and output it as comma-separated rows, one session per line, '
        + 'with these fields in this exact order:\n' + numbered + '\n\n'
        + 'Rules:\n'
        + '- Separate fields with a comma.\n'
        + '- If a field isn’t shown for a session, leave it blank but keep its comma; trailing fields at the end of a line (e.g. Teacher) can be left off entirely.\n'
        + 'Output only the rows — no headers, totals or extra commentary, no code block.';
}
// Grid-paste prompt (days x periods) -- shared by Saturday and Holiday, the
// two layouts whose "day" row can carry more than one class/stream.
var GRID_INTRO={
    saturday:'Read this Saturday class timetable',
    holiday:'Read this holiday lesson timetable',
};
function buildGridPrompt(){
    var isHoliday = el('layout').value === 'holiday';
    var dayLine = isHoliday
        ? '- Each next line: the date (write it as a date if one is shown, otherwise the day name), then the subject '
          + 'in each period in order. Put the teacher in brackets, e.g. Maths (Mr A). Leave a cell empty for a free '
          + 'period or break.\n'
        : '- Each next line: the day, then the subject in each period in order. Put the teacher in brackets, e.g. '
          + 'Maths (Mr A). Leave a cell empty for a free period or break.\n';
    return (GRID_INTRO[el('layout').value] || 'Read this class timetable')
        + ' (photo, screenshot or spreadsheet) and output it as a comma-separated grid, one row per line:\n'
        + '- First line: the word "Day", then each period\'s time range — e.g. Day, 8:00-9:00, 9:00-10:00, 10:00-11:00\n'
        + dayLine
        + '- If more than one class/stream has DIFFERENT subjects on the same day (e.g. Science vs Arts), '
        + 'give each its own line for that day, with the class/stream in brackets right after it — '
        + 'e.g. Monday (Science), Maths (Mr A), ...  then  Monday (Arts), Government, ...  on the next line. '
        + 'Skip the brackets entirely if every class follows the same timetable.\n'
        + '- If the rest of a day is a single activity (e.g. Skill Acquisition), repeat that exact same text in every '
        + 'remaining period so it merges into one block — do NOT write it only once.\n'
        + '- If a cell shows more than one subject for the same period (e.g. "PHY/GOVT" for a split class), keep it '
        + 'exactly as written, slash and all — do NOT treat anything after a "/" as a teacher name.\n'
        + 'Output only the rows — no headings, totals or extra text, no code block.';
}
function blankRow(){ return {week:'',date:'',day:'',group:'',time:'',dur:'60',subject:'',teacher:'',venue:''}; }
function normTime(t){
    t=(t||'').trim(); if(!t) return '';
    var m=t.match(/^(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?$/i); if(!m) return t;
    var h=+m[1], mi=m[2]?+m[2]:0;
    if(m[3]){ var pm=/pm/i.test(m[3]); if(h===12) h=pm?12:0; else if(pm) h+=12; }
    return ('0'+h).slice(-2)+':'+('0'+mi).slice(-2);
}
function renderEditor(){
    el('sessHint').textContent = layout().hint || '';
    el('bulkHint').textContent = 'One session per line, in this order: ' +
        layout().fields.map(function(f){ return BULK_SHORT[f]; }).join(', ') +
        '. Separate with a comma, a | or a tab (paste straight from Excel/Sheets). Trailing fields can be left out.';
    el('tt-bulk-prompt').textContent = buildBulkPrompt();
    el('tt-ai-prompt').textContent = buildGridPrompt();
    el('rowBody').innerHTML = rows.map(sessCard).join('');
}
function focusCard(i){
    var card=document.querySelector('#rowBody .sess-card[data-i="'+i+'"]'); if(!card) return;
    var s=card.querySelector('[data-f="subject"]')||card.querySelector('input'); if(s) s.focus();
}
// New session inherits the previous one's day/stream/duration/venue and auto-
// advances the start time by the duration, so building a day's periods is just
// "type subject, Add, type subject, Add…".
function addRow(){
    var last=rows[rows.length-1], r=blankRow();
    if(last){
        r.week=last.week; r.date=last.date; r.day=last.day; r.group=last.group; r.dur=last.dur; r.venue=last.venue;
        r.time=(last.time && last.dur)?addMinutes(last.time,last.dur):last.time;
    }
    rows.push(r); renderEditor(); renderSheet(); focusCard(rows.length-1);
}
function dupRow(i){ rows.splice(i+1,0,Object.assign({},rows[i])); renderEditor(); renderSheet(); focusCard(i+1); }
function delRow(i){ rows.splice(i,1); renderEditor(); renderSheet(); }
function clearRows(){ if(rows.length && !confirm('Clear all sessions?')) return; rows=[]; addRow(); }
// Some quick-add columns have a recognisable value shape — used to re-align a
// line that's missing a comma so later values don't shift into the wrong field.
var TT_STRONG={date:1,day:1,time:1,dur:1};
// Day names incl. common abbreviations (Tue/Tues/Wed/Weds/Thu/Thur/Thurs…),
// each mapped to its canonical full name so sorting/grouping stays consistent.
var DAY_ALIAS={mon:'Monday',monday:'Monday',tue:'Tuesday',tues:'Tuesday',tuesday:'Tuesday',
    wed:'Wednesday',weds:'Wednesday',wednesday:'Wednesday',thu:'Thursday',thur:'Thursday',
    thurs:'Thursday',thursday:'Thursday',fri:'Friday',friday:'Friday',sat:'Saturday',
    saturday:'Saturday',sun:'Sunday',sunday:'Sunday'};
function canonDay(v){ return DAY_ALIAS[(v||'').trim().toLowerCase().replace(/\.+$/,'')] || (v||'').trim(); }
// Matches a weekday name/abbreviation at the START of a string, with an
// optional trailing "." and/or "," before whatever follows — used to strip a
// day name sitting in front of a date in the same cell (see parseDayCell).
var DAY_PREFIX_RE = new RegExp('^(' + Object.keys(DAY_ALIAS).join('|') + ')\\.?,?\\s+', 'i');
function ttLooks(field, v){
    v=(v||'').trim(); if(!v) return false;
    if(field==='date') return !!parseDateAny(v);
    if(field==='day') return !!DAY_ALIAS[v.toLowerCase().replace(/\.+$/,'')];
    if(field==='time'){ var m=v.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/i);
        if(!m) return false; var h=+m[1]; return m[3]?(h>=1&&h<=12):(h>=0&&h<=23); }
    if(field==='dur') return /^\d{1,3}$/.test(v);
    return false;
}
// Best-effort repair for a quick-add line missing one or more commas: walk the
// expected fields and the pasted cells together; a strongly-typed field whose
// value doesn't match its shape (or a free-text field sitting on a value that
// clearly belongs to a later typed field) is treated as omitted and a blank is
// inserted — so e.g. a missing Class/Stream no longer shoves the time into the
// duration column. A present-but-empty cell (e.g. a leading ", " to skip the
// date) is a real blank value and is kept in place. Correctly-sized lines are
// returned unchanged, and trailing fields (e.g. Teacher) may simply be left off.
function realignBulk(parts, fields){
    parts=parts.slice(); var n=fields.length;
    if(parts.length>=n) return parts;
    var laterStrong=[];
    for(var i=0;i<n;i++){ var s={}; for(var j=i+1;j<n;j++){ if(TT_STRONG[fields[j]]) s[fields[j]]=1; } laterStrong.push(s); }
    var out=[], ci=0;
    for(var fi=0;fi<n;fi++){
        var f=fields[fi];
        if(ci>=parts.length){ out.push(''); continue; }
        var cell=(parts[ci]||'').trim(), short=(parts.length-ci)<(n-fi);
        if(cell===''){ out.push(parts[ci]); ci++; continue; }   // present-but-blank value
        if(TT_STRONG[f]){
            if(ttLooks(f,cell)){ out.push(parts[ci]); ci++; }
            else out.push('');                       // typed value omitted here
        } else {
            var belongsLater=false;
            if(short){ for(var t in laterStrong[fi]){ if(ttLooks(t,cell)){ belongsLater=true; break; } } }
            if(belongsLater) out.push('');            // this field's value was omitted
            else { out.push(parts[ci]); ci++; }
        }
    }
    while(ci<parts.length){ out.push(parts[ci]); ci++; }
    return out.length>n ? out.slice(0,n) : out;
}
function bulkAdd(){
    var lines=(el('bulkText').value||'').split('\n'), fields=layout().fields, added=0;
    lines.forEach(function(line){
        if(!line.trim()) return;
        var parts = line.indexOf('\t')>=0 ? line.split('\t') : line.split(/\s*[|,]\s*/);
        parts = realignBulk(parts, fields);          // repair a missing comma
        var r=blankRow();
        fields.forEach(function(f,idx){
            if(idx<parts.length){
                var val=(parts[idx]||'').trim();
                r[f] = (f==='time') ? normTime(val)
                     : (f==='date') ? toISO(val)
                     : (f==='day') ? canonDay(val) : val;
            }
        });
        if(r.date && !r.day){ var a=dayFromDate(r.date); if(a) r.day=a; }
        rows.push(r); added++;
    });
    if(added){ el('bulkText').value=''; renderEditor(); renderSheet(); }
}

// ---------- fastest: paste a whole day×period grid ----------
function splitCells(line){
    return line.indexOf('\t') >= 0 ? line.split('\t') : line.split(/\s*[|,]\s*/);
}
function parsePeriodCell(s){
    s = (s || '').trim(); if(!s) return null;
    var m = s.split(/\s*[-–—]\s*/);
    var start = normTime(m[0]), dur = '60';
    if(m.length > 1){
        var end = normTime(m[1]), a = start.split(':'), b = end.split(':');
        if(a.length === 2 && b.length === 2){
            var d = (+b[0] * 60 + +b[1]) - (+a[0] * 60 + +a[1]);
            if(d > 0) dur = String(d);
        }
    }
    return {time: start, dur: dur};
}
function parseSubjectCell(s){
    s = (s || '').trim(); var teacher = '';
    // "Subject (Teacher)" is the one documented/taught syntax (see the
    // grid-paste hint and its AI prompt). A bare "/" is deliberately left
    // alone rather than split into subject/teacher -- it's common for a cell
    // to pack more than one subject into a single period this way (e.g.
    // "PHY/GOVT" for parallel stream options sitting together), and treating
    // every "/" as a teacher separator silently mangled those into a bogus
    // "teacher" field.
    var m = s.match(/^(.*?)\s*[\(（](.+?)[\)）]\s*$/);     // "Subject (Teacher)"
    if(m){ s = m[1].trim(); teacher = m[2].trim(); }
    return {subject: s, teacher: teacher};
}
// The day/date cell may carry a trailing "(Class/Stream)" the same way a
// subject cell carries "(Teacher)" -- e.g. "Monday (Science)" -- so more than
// one class can share a day: give each its own line with its own group.
function parseDayCell(s){
    s = (s || '').trim(); var group = '';
    var m = s.match(/^(.*?)\s*[\(（](.+?)[\)）]\s*$/);
    if(m){ s = m[1].trim(); group = m[2].trim(); }
    // A leading weekday name/abbreviation before the date itself (e.g. "SAT
    // 1/10/2026", "Saturday, 1/10/2026") is common when pasting straight from
    // a spreadsheet that shows both in one cell. parseDateAny only recognises
    // a cell that's JUST a date, so left as-is this never parses and the
    // whole string ends up shown as one unsplit line instead of the day on
    // top and the date underneath. Strip the prefix -- but only when a real
    // date follows it, so a plain "Saturday" (no date) is left untouched.
    var dp = s.match(DAY_PREFIX_RE);
    if(dp){
        var rest = s.slice(dp[0].length).trim();
        if(parseDateAny(rest)) s = rest;
    }
    return {label: s, group: group};
}
function gridPaste(){
    var lines = (el('gridPasteText').value || '').split('\n').filter(function(s){ return s.trim(); });
    if(lines.length < 2){ alert('Add a header line of period times and at least one day row.'); return; }
    var header = splitCells(lines[0]);
    var periods = header.slice(1).map(parsePeriodCell);   // first cell = the "Day" label
    var added = 0;
    for(var li = 1; li < lines.length; li++){
        var cells = splitCells(lines[li]);
        var first = (cells[0] || '').trim();
        if(!first) continue;
        var dc = parseDayCell(first);
        var day = dc.label, date = '', group = dc.group;
        if(parseDateAny(dc.label)){ date = toISO(dc.label); day = dayFromDate(dc.label) || dc.label; }
        for(var pi = 0; pi < periods.length; pi++){
            var p = periods[pi]; if(!p) continue;
            var sc = parseSubjectCell(cells[pi + 1] || '');
            if(!sc.subject) continue;
            var r = blankRow();
            r.day = day; r.date = date; r.time = p.time; r.dur = p.dur;
            r.subject = sc.subject; r.teacher = sc.teacher; r.group = group;
            rows.push(r); added++;
        }
    }
    if(added){ el('gridPasteText').value = ''; renderEditor(); renderSheet(); }
    else alert('Nothing added — check the grid format.');
}

// ---------- fill the remaining periods of a day with one activity ----------
function fillRestOfDay(){
    var day = canonDay((el('fillDay').value || '').trim());
    var act = (el('fillAct').value || '').trim();
    if(!day){ alert('Choose a day to fill (e.g. Friday).'); return; }
    if(!act){ alert('Type the activity to fill (e.g. Skill Acquisition).'); return; }
    function rowDay(r){ return canonDay((r.date ? dayFromDate(r.date) : '') || (r.day || '').trim()); }
    var dayRows = rows.filter(function(r){ return !isAll(r.group) && r.time && rowDay(r) === day; });
    if(!dayRows.length){ alert('No sessions found for ' + day + ' yet — add its lessons first.'); return; }
    // periods across the whole timetable, in time order
    var pmap = {}, periods = [];
    rows.forEach(function(r){ if(!r.time || isAll(r.group)) return; var k = periodKey(r);
        if(!pmap[k]){ pmap[k] = {time: r.time, dur: r.dur || '60', k: k}; periods.push(pmap[k]); } });
    periods.sort(function(a, b){ return a.time.localeCompare(b.time); });
    // the streams present that day (else a single unnamed group)
    var gset = {}, groups = [];
    dayRows.forEach(function(r){ var g = (r.group || '').trim(); if(!(g in gset)){ gset[g] = 1; groups.push(g); } });
    if(!groups.length) groups = [''];
    // the date this day maps to, if the timetable is date-based
    var date = ''; for(var i = 0; i < dayRows.length; i++){ if(dayRows[i].date){ date = dayRows[i].date; break; } }
    // last period (in order) that already has any lesson this day → fill only AFTER it
    var lastFilled = -1;
    periods.forEach(function(p, idx){
        if(dayRows.some(function(r){ return r.subject && periodKey(r) === p.k; })) lastFilled = idx; });
    // which (period,group) already hold a subject this day — never overwrite those
    var have = {};
    dayRows.forEach(function(r){ if(r.subject) have[periodKey(r) + '§' + (r.group || '').trim()] = 1; });
    var added = 0;
    periods.forEach(function(p, idx){
        if(idx <= lastFilled) return;                    // keep the lessons; fill the tail
        groups.forEach(function(g){
            if(have[p.k + '§' + g]) return;
            var r = blankRow();
            r.day = day; r.date = date; r.time = p.time; r.dur = p.dur; r.subject = act; r.group = g;
            rows.push(r); added++;
        });
    });
    if(added){ renderEditor(); renderSheet(); }
    else alert('Nothing to fill — every period on ' + day + ' already has an entry.');
}

// Custom table paste: first line = the column headers, each next line = a row.
// Fills the auto-numbered grid (the S/N column is added automatically).
function listPaste(){
    var lines = (el('listPasteText').value || '').split('\n').filter(function(s){ return s.trim(); });
    if(lines.length < 1){ alert('Paste at least a header line, then one row per line.'); return; }
    var headers = splitCells(lines[0]).map(function(s){ return s.trim(); }).filter(Boolean);
    if(headers.length) el('gridCols').value = headers.join(', ');
    rosterCells = {};
    var dataLines = lines.slice(1);
    dataLines.forEach(function(line, ri){
        splitCells(line).forEach(function(v, ci){
            v = (v || '').trim();
            if(v) rosterCells[ri + ':' + ci] = v;
        });
    });
    el('listRows').value = Math.max(1, dataLines.length);
    el('listPasteText').value = '';
    renderSheet();
}

document.addEventListener('input', function(e){
    var card=e.target.closest && e.target.closest('#rowBody .sess-card');
    if(card){
        var i=parseInt(card.dataset.i,10), f=e.target.dataset.f;
        if(f){ rows[i][f]=e.target.value;
            if(f==='date'){ var auto=dayFromDate(e.target.value); if(auto){ rows[i].day=auto;
                var di=card.querySelector('[data-f="day"]'); if(di) di.value=auto; } }
            if(f==='week') renderManageSaturdays(); }
        renderSheet();
    } else if(['title','subtitle','school','gridCols','gridRows','listRows'].indexOf(e.target.id)>=0){
        renderSheet();
    }
});

// ---------- printable sheet ----------
function renderHead(){
    el('pSchool').textContent = el('school').value || '';
    var ttl = el('title').value || layout().title || 'Timetable';
    if(isTimeline() || isGazette() || isSwiss()){
        var w=ttl.trim().split(/\s+/), last=w.pop();
        el('pTitle').innerHTML = (w.length?esc(w.join(' '))+' ':'')+'<span class="tl-gold">'+esc(last||'')+'</span>';
    } else if(isNotebook()) el('pTitle').innerHTML='<span class="nb-big">'+esc(ttl)+'</span>';
    else el('pTitle').textContent = ttl;
    var sub=el('subtitle').value;
    if(_pageLabel) sub = (sub ? sub+' · ' : '') + _pageLabel;   // multi-page export
    el('pSub').textContent=sub; el('pSub').style.display=sub?'block':'none';
}

// Day/Date × time-period grid: rows are days (or dates), each day may hold
// several Class/Stream sub-rows, columns are the time slots. Cells identical
// across every group in a period are merged vertically; a "All" group makes a
// full-width band (e.g. Mock Examination).
function cellInner(arr){
    return arr.map(function(r){
        return (r.subject?'<span class="c-subj">'+esc(r.subject)+'</span>':'')
             + (r.teacher?'<span class="c-tchr">'+esc(r.teacher)+'</span>':'');
    }).join('<hr class="c-sep">');
}
function renderGridModeSheet(){
    // period columns come from real sessions (banners/All excluded)
    var pmap={}, periods=[];
    rows.forEach(function(r){ if(r.time && !isAll(r.group)){ var k=periodKey(r);
        if(!pmap[k]){ pmap[k]={k:k,label:periodLabel(r),start:r.time}; periods.push(pmap[k]); } } });
    periods.sort(function(a,b){ return a.start.localeCompare(b.start); });

    var anyGroup = rows.some(function(r){ return (r.group||'').trim() && !isAll(r.group); });
    var dmap={}, order=[];
    rows.forEach(function(r){
        var date=r.date||'';
        var day=(date?dayFromDate(date):'') || (r.day||'').trim() || '—';
        var key=date||day;
        if(!dmap[key]){ dmap[key]={day:day, date:date, label:(r.daylabel||''),
            sort:(parseDateAny(date)?parseDateAny(date).iso:('zz'+('0'+dayRank(day)).slice(-2))),
            groups:[], gset:{}, cells:{}, banners:[]}; order.push(key); }
        var d=dmap[key];
        if(date && !d.date) d.date=date;
        if(isAll(r.group)){ if(r.subject||r.teacher) d.banners.push(r); return; }
        var g=(r.group||'').trim();
        if(!(g in d.gset)){ d.gset[g]=1; d.groups.push(g); }
        if(r.time){ var ck=g+'§'+periodKey(r); (d.cells[ck]=d.cells[ck]||[]).push(r); }
    });
    order.sort(function(a,b){ return String(dmap[a].sort).localeCompare(String(dmap[b].sort)); });

    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the grid.</p>';
        return;
    }
    var spanAll = (anyGroup?1:0) + periods.length;
    var thead='<tr><th>Day</th>'+(anyGroup?'<th>Class / Stream</th>':'')
            + periods.map(function(p){ return '<th>'+esc(p.label)+'</th>'; }).join('')+'</tr>';

    // Each day becomes its own <tbody class="day"> so a thick rule can separate
    // one day's block from the next (see the CSS above) — on screen and export.
    var body='';
    order.forEach(function(key){
        var d=dmap[key];
        var dh='';
        // dates with only a banner (e.g. Mock Examination) get no empty group row
        var groups = anyGroup ? d.groups.slice() : [''];
        var totalRows = groups.length + d.banners.length;
        if(totalRows===0) totalRows=1;
        var dlabel=esc(d.label || d.day || dayFromDate(d.date) || '—');
        if(d.date){ dlabel+='<br><span class="c-date">'+esc(fmtDate(d.date))+'</span>'; }
        var first=true;
        // Merge blocks: a RUN of consecutive periods whose content is identical
        // across every group becomes ONE rectangular cell — colspan = periods in
        // the run, rowspan = number of groups. This collapses e.g. a trailing
        // "Skill Acquisition" that fills the rest of a day for ANY run (periods
        // 2–4, 3–4, the whole day, …), not only the whole day. Normal periods
        // still render per group; a single uniform period keeps its vertical
        // (rowspan) merge as before.
        var uval = periods.map(function(p){
            var vals = groups.map(function(g){ return cellInner(d.cells[g+'§'+p.k]||[]); });
            return (vals[0] && vals.every(function(v){ return v===vals[0]; })) ? vals[0] : null;
        });
        var runStart=[], runLen=[];
        for(var pi=0; pi<periods.length;){
            if(uval[pi]!==null){
                var pj=pi+1; while(pj<periods.length && uval[pj]===uval[pi]) pj++;
                for(var pk=pi; pk<pj; pk++){ runStart[pk]=pi; runLen[pk]=pj-pi; }
                pi=pj;
            } else { runStart[pi]=-1; runLen[pi]=0; pi++; }
        }
        groups.forEach(function(g, gi){
            dh+='<tr>';
            if(first){ dh+='<th rowspan="'+totalRows+'" class="day-cell">'+dlabel+'</th>'; first=false; }
            if(anyGroup) dh+='<td class="grp-cell">'+esc(g||'—')+'</td>';
            periods.forEach(function(p, pidx){
                if(uval[pidx]!==null){
                    // only the top-left cell of each merge rectangle is emitted;
                    // the cells it covers (other columns/rows) are skipped
                    if(gi===0 && runStart[pidx]===pidx){
                        var cs=runLen[pidx], rs=groups.length;
                        dh+='<td class="cell merged'+(cs>1?' wide':'')+'"'
                          + (cs>1?(' colspan="'+cs+'"'):'')
                          + (rs>1?(' rowspan="'+rs+'"'):'')
                          + '>'+uval[pidx]+'</td>';
                    }
                    return;
                }
                dh+='<td class="cell">'+cellInner(d.cells[g+'§'+p.k]||[])+'</td>';
            });
            dh+='</tr>';
        });
        d.banners.forEach(function(b){
            dh+='<tr>';
            if(first){ dh+='<th rowspan="'+totalRows+'" class="day-cell">'+dlabel+'</th>'; first=false; }
            dh+='<td class="cell banner" colspan="'+spanAll+'">'
                + (b.subject?'<span class="c-subj">'+esc(b.subject)+'</span>':'')
                + (b.teacher?'<span class="c-tchr">'+esc(b.teacher)+'</span>':'')
                + '</td></tr>';
        });
        body+='<tbody class="day">'+dh+'</tbody>';
    });
    el('pBody').innerHTML='<table class="grid-tt"><thead>'+thead+'</thead>'+body+'</table>';
}

// A small, harmonious palette assigned consistently per group (first-seen
// order), so a few Class/Stream groups get calm, muted tints — not a clashing
// colour per group.
var GROUP_PALETTE = ['#eef2ff','#ecfdf5','#fff7ed','#fdf2f8','#f0f9ff','#f5f3ff'];
var _groupColors = {};
function buildGroupColors(){
    _groupColors = {}; var i=0;
    rows.forEach(function(r){ var g=(r.group||'').trim();
        if(g && !isAll(r.group) && !(g in _groupColors)){ _groupColors[g]=GROUP_PALETTE[i % GROUP_PALETTE.length]; i++; } });
}
function groupBlock(r){
    var g=(r.group||'').trim();
    var bg=_groupColors[g]||'';
    return '<div class="g-block"'+(bg?(' style="background:'+bg+'"'):'')+'>'
        + (g?'<span class="g-tag">'+esc(g)+'</span>':'')
        + (r.subject?'<span class="c-subj">'+esc(r.subject)+'</span>':'')
        + (r.teacher?'<span class="c-tchr">'+esc(r.teacher)+'</span>':'')
        + '</div>';
}
// Days as COLUMNS (time down the left). Multiple groups in a (period, day) cell
// sit side by side; an "All" group at a period makes a full-width band (BREAK).
function renderGridColumnsSheet(){
    buildGroupColors();
    var pmap={}, periods=[];
    rows.forEach(function(r){ if(!r.time) return; var k=periodKey(r);
        if(!pmap[k]){ pmap[k]={k:k,label:periodLabel(r),start:r.time,allText:''}; periods.push(pmap[k]); }
        if(isAll(r.group) && (r.subject||r.teacher)){
            var sig=(r.subject||'')+'|'+(r.teacher||'');
            pmap[k]._seen = pmap[k]._seen || {};
            if(!pmap[k]._seen[sig]){ pmap[k]._seen[sig]=1;
                pmap[k].allText += (r.subject?'<span class="c-subj">'+esc(r.subject)+'</span>':'')
                                 + (r.teacher?'<span class="c-tchr">'+esc(r.teacher)+'</span>':''); } }
    });
    periods.sort(function(a,b){ return a.start.localeCompare(b.start); });

    var dseen={}, dayList=[];
    rows.forEach(function(r){ if(isAll(r.group)) return;
        var date=r.date||'', day=(date?dayFromDate(date):'')||(r.day||'').trim()||'—', key=date||day;
        if(!(key in dseen)){ dseen[key]={day:day,date:date,
            sort:(parseDateAny(date)?parseDateAny(date).iso:('zz'+('0'+dayRank(day)).slice(-2)))}; dayList.push(key); } });
    dayList.sort(function(a,b){ return String(dseen[a].sort).localeCompare(String(dseen[b].sort)); });

    if(!periods.length || !dayList.length){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the grid.</p>';
        return;
    }
    var cells={};
    rows.forEach(function(r){ if(!r.time||isAll(r.group)) return;
        var date=r.date||'', day=(date?dayFromDate(date):'')||(r.day||'').trim()||'—', dk=date||day, pk=periodKey(r);
        (cells[pk]=cells[pk]||{}); (cells[pk][dk]=cells[pk][dk]||[]).push(r); });

    var thead='<tr><th>Time</th>'+dayList.map(function(dk){ var d=dseen[dk];
        var lbl=esc(d.day||'—'); if(d.date) lbl+='<br><span class="c-date">'+esc(fmtDate(d.date))+'</span>';
        return '<th class="day-col">'+lbl+'</th>'; }).join('')+'</tr>';

    // Per (period, day) inner html, then merge a RUN of consecutive periods that
    // hold identical content within a day column into one cell (rowspan) — the
    // "rest of the day is Skill Acquisition" case, mirroring the day-row grid. A
    // full-width band period (p.allText) breaks any run.
    var inner={};
    periods.forEach(function(p,pi){ if(p.allText) return;
        dayList.forEach(function(dk){
            var arr=(cells[p.k] && cells[p.k][dk]) || [];
            inner[pi+'|'+dk] = arr.length ? ('<div class="g-row">'+arr.map(groupBlock).join('')+'</div>') : '';
        }); });
    var span={}, skip={};
    dayList.forEach(function(dk){
        var pi=0;
        while(pi<periods.length){
            if(periods[pi].allText){ pi++; continue; }
            var html=inner[pi+'|'+dk]||'';
            if(html){
                var pj=pi+1;
                while(pj<periods.length && !periods[pj].allText && (inner[pj+'|'+dk]||'')===html) pj++;
                if(pj-pi>1){ span[pi+'|'+dk]=pj-pi; for(var k=pi+1;k<pj;k++) skip[k+'|'+dk]=true; }
                pi=pj;
            } else pi++;
        }
    });
    var body='';
    periods.forEach(function(p,pi){
        body+='<tr><th class="time-cell">'+esc(p.label)+'</th>';
        if(p.allText){
            body+='<td class="cell banner" colspan="'+dayList.length+'">'+p.allText+'</td>';
        } else {
            dayList.forEach(function(dk){
                var kk=pi+'|'+dk;
                if(skip[kk]) return;                       // covered by a rowspan above
                var rs=span[kk], html=inner[kk]||'';
                var cls='cell day-col'+(rs?' merged':'')+((rs&&html)?' wide':'');
                body+='<td class="'+cls+'"'+(rs?(' rowspan="'+rs+'"'):'')+'>'+html+'</td>';
            });
        }
        body+='</tr>';
    });
    el('pBody').innerHTML='<table class="grid-tt cols"><thead>'+thead+'</thead><tbody>'+body+'</tbody></table>';
}

// Exam list: one row per exam, with a blank signature column.
function renderListSheet(){
    var fields=layout().fields;
    var labels={date:'Date', time:'Time', subject:'Subject', teacher:'Invigilator', venue:'Venue'};
    var printCols=fields.filter(function(c){ return c!=='dur'; });
    var thead='<tr>'+printCols.map(function(c){ return '<th>'+labels[c]+'</th>'; }).join('')
            + '<th class="sig-col">Invigilator&#39;s Signature</th></tr>';
    var sorted=rows.slice().sort(function(a,b){
        return (a.date||'').localeCompare(b.date||'') || (a.time||'').localeCompare(b.time||''); });
    var body=sorted.map(function(r){
        return '<tr>'+printCols.map(function(c){
            var v = c==='time' ? periodLabel(r) : (c==='date' ? fmtDate(r[c]) : (r[c]||''));
            return '<td>'+esc(v)+'</td>';
        }).join('')+'<td class="empty sig-col"></td></tr>';
    }).join('');
    if(!body) body='<tr><td colspan="'+(printCols.length+1)+'" style="text-align:center;color:#888">Add exams above to build the timetable.</td></tr>';
    el('pBody').innerHTML='<table><thead>'+thead+'</thead><tbody>'+body+'</tbody></table>';
}

// Shared column-width calculator for every blankgrid-family table (Blank
// Custom Grid, Sweeping Roster, Custom List/Table) — the one place that
// decides how wide the leading label/S-N column is vs. how the rest of the
// table's width is split among the N normal data columns, so a table with
// 3, 5, 7… columns is always proportioned the same predictable way instead
// of leaving it to the browser's content-based auto table layout (which is
// what let one column silently absorb the table's spare width — see the
// .blankgrid CSS comment above). Called once per render, for the live sheet
// and for the export snapshot alike, so both are always identical.
//   special: 'sn'    — a numbers-only S/N column (Custom List/Table)
//            'label' — a text row-label column (WEEK/DAY/blank-grid rows)
//            null    — no special column; every column shares equally
function specialColPct(special){ return special==='sn' ? 8 : 18; }
function colGroupHTML(numNormal, special){
    numNormal = Math.max(0, numNormal|0);
    var specialPct = special ? specialColPct(special) : 0;
    var normalPct = numNormal>0 ? (100-specialPct)/numNormal : 0;
    var cols = special ? ['<col style="width:'+specialPct+'%">'] : [];
    for(var i=0;i<numNormal;i++) cols.push('<col style="width:'+normalPct+'%">');
    return '<colgroup>'+cols.join('')+'</colgroup>';
}

function renderBlankGridSheet(){
    var roster=isRoster();
    var cols=(el('gridCols').value||'').split(',').map(function(s){return s.trim();}).filter(Boolean);
    // Auto-numbered custom table: a leading S/N column + N editable rows.
    if(isListTable()){
        var n=Math.max(1, Math.min(200, parseInt(el('listRows').value,10)||10));
        var lcolgroup=colGroupHTML(cols.length, 'sn');
        var lthead='<tr><th class="sn-col">S/N</th>'+cols.map(function(c){return '<th class="col-sep">'+esc(c)+'</th>';}).join('')+'</tr>';
        var lbody='';
        for(var ri=0; ri<n; ri++){
            lbody+='<tr><th class="sn-col">'+(ri+1)+'</th>'+cols.map(function(c,ci){
                var k=ri+':'+ci;
                return '<td class="roster-cell col-sep" contenteditable="true" data-rc="'+k+'" data-ph="">'+esc(rosterCells[k]||'')+'</td>';
            }).join('')+'</tr>';
        }
        el('pBody').innerHTML='<table class="grid-tt blankgrid listtable">'+lcolgroup+'<thead>'+lthead+'</thead><tbody>'+lbody+'</tbody></table>';
        return;
    }
    var rws=(el('gridRows').value||'').split('\n').map(function(s){return s.trim();}).filter(Boolean);
    var corner = roster ? (el('layout').value==='roster_week' ? 'Week' : 'Day') : '';
    var colgroup=colGroupHTML(cols.length, 'label');
    var thead='<tr><th>'+esc(corner)+'</th>'+cols.map(function(c){return '<th class="col-sep">'+esc(c)+'</th>';}).join('')+'</tr>';
    var body=rws.map(function(rl,ri){
        return '<tr><th>'+esc(rl)+'</th>'+cols.map(function(c,ci){
            // Every cell is fillable — type straight into the grid to build ANY
            // timetable (subjects, names, notes …). Cells persist in rosterCells
            // and are captured by the PDF/image export. Leave a cell blank to
            // print it empty and fill by hand. Rosters show a "Name" placeholder.
            var k=ri+':'+ci;
            return '<td class="roster-cell col-sep" contenteditable="true" data-rc="'+k+'" data-ph="'+(roster?'Name':'')+'">'
                 + esc(rosterCells[k]||'')+'</td>';
        }).join('')+'</tr>';
    }).join('');
    el('pBody').innerHTML='<table class="grid-tt blankgrid'+(roster?' roster':'')+'">'+colgroup+'<thead>'+thead+'</thead><tbody>'+body+'</tbody></table>';
}

// ---------- Saturday plan: first-Saturday date + lesson-free cascade ----------
// The Saturday timetable is ordered by WEEK; the actual date of each week is
// computed from the first Saturday, skipping any Saturday marked lesson-free.
// Marking a Saturday free shrinks the list of available Saturdays, so that week
// and every later week automatically shift to the next Saturday(s).
var saturdayPlan = { first:'', free:{} };   // free: { 'YYYY-MM-DD': true }
function isSaturdayLayout(){ return el('layout').value==='saturday'; }
function addDaysISO(iso, days){
    var p=parseDateAny(iso); if(!p) return '';
    var d=new Date(p.y, p.m-1, p.d); d.setDate(d.getDate()+days);
    return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
}
function weeksInUse(){
    var s={}; rows.forEach(function(r){ var w=parseInt(r.week,10); if(w>=1) s[w]=1; });
    return Object.keys(s).map(Number).sort(function(a,b){ return a-b; });
}
// Generate consecutive Saturdays from the first date, assign each non-free one to
// the next week, and offer a few spare upcoming Saturdays that can be freed too.
function computeSaturdayDates(){
    var first=saturdayPlan.first, weeks=weeksInUse();
    var maxWeek=weeks.length?weeks[weeks.length-1]:0;
    var out={ weekDate:{}, saturdays:[] };
    if(!parseDateAny(first)) return out;
    var iso=first, wk=0, extra=0, guard=0;
    while(guard++ < 520){
        var free=!!saturdayPlan.free[iso];
        var e={iso:iso, free:free, week:0};
        if(!free){ wk++; e.week=wk; out.weekDate[wk]=iso; }
        out.saturdays.push(e);
        if(wk>=maxWeek){ extra++; if(extra>=5) break; }   // a few spare Saturdays to offer
        iso=addDaysISO(iso, 7);
    }
    return out;
}
// Stamp the computed date + a "Week N" label onto each Saturday session so the
// generic grid renderer groups and sorts them by cascaded date.
function applySaturdayDates(){
    if(!isSaturdayLayout()) return;
    var map=computeSaturdayDates().weekDate;
    rows.forEach(function(r){
        var w=parseInt(r.week,10);
        if(w>=1){ r.daylabel='Week '+w; r.day='Week '+w; r.date=map[w]||''; }
        // A row with no week number but its OWN explicit date (e.g. pasted
        // via the grid-paste box, which sets day/date directly) keeps that
        // date rather than having it wiped — only a genuinely blank row
        // (no week, no date) gets cleared.
        else if(!r.date){ r.daylabel=''; }
    });
}
function renderManageSaturdays(){
    var box=el('satManage'); if(!box) return;
    if(!isSaturdayLayout()){ box.innerHTML=''; return; }
    el('satFirst').value=saturdayPlan.first||'';
    var info=computeSaturdayDates();
    if(!info.saturdays.length){
        box.innerHTML='<p class="sess-hint" style="margin:0">Set the first Saturday’s date above, then tick any Saturday that won’t hold lessons.</p>';
        return;
    }
    box.innerHTML=info.saturdays.map(function(s){
        var tag=s.free ? '<span class="s-wk">No lessons</span>'
                       : '<span class="s-wk">Week '+s.week+'</span>';
        return '<label class="sat-chip'+(s.free?' free':'')+'">'
             + '<input type="checkbox" data-iso="'+s.iso+'"'+(s.free?' checked':'')+'> '
             + tag+' · '+esc(fmtDate(s.iso))+'</label>';
    }).join('');
}

// ---------- save / load / list named designs ----------
var currentDesignId = null;
// The only page-specific values this (otherwise static, cacheable) file
// needs — read from a small JSON island the template renders, instead of
// this file itself being server-templated, so it can be served from
// /static/ and cached across visits like any other JS asset.
var DESIGNER_CONFIG = JSON.parse(document.getElementById('designer-config').textContent);
var URL_SAVE = DESIGNER_CONFIG.urls.save;
var URL_LIST = DESIGNER_CONFIG.urls.list;
var URL_LOAD = DESIGNER_CONFIG.urls.load_base;
var URL_DEL  = DESIGNER_CONFIG.urls.delete_base;
var INITIAL_SAVED = DESIGNER_CONFIG.saved;
var LAYOUT_LABEL={saturday:'Saturday classes',holiday:'Holiday lessons',exam:'Examination',
                  grid:'Blank grid',list_table:'Custom table',roster_week:'Weekly roster',roster_day:'Daily roster'};
function labelForLayout(k){ return LAYOUT_LABEL[k]||k||''; }

function collectState(){
    return { v:1, layout:el('layout').value, theme:el('theme').value,
        school:el('school').value, title:el('title').value,
        titleTouched:!!el('title').dataset.touched, subtitle:el('subtitle').value,
        orient:el('orient').value, gridCols:el('gridCols').value, gridRows:el('gridRows').value,
        rosterCount:el('rosterCount').value, listRows:el('listRows').value,
        showLogo:el('showLogo')?el('showLogo').checked:true,
        rows:rows, rosterCells:rosterCells, saturday:saturdayPlan };
}
function applyState(s){
    if(!s) return;
    el('layout').value=s.layout||'saturday';
    // Themes that no longer exist (Modern, Classic, Ocean, ...) fall back to
    // the first theme, Timeline, so older saved timetables still open.
    var th=el('theme');
    th.value = (s.theme && th.querySelector('option[value="'+s.theme+'"]')) ? s.theme : th.options[0].value;
    el('school').value=s.school||'';
    el('subtitle').value=s.subtitle||'';
    el('orient').value=s.orient||'rows';
    if(s.gridCols!=null) el('gridCols').value=s.gridCols;
    if(s.gridRows!=null) el('gridRows').value=s.gridRows;
    if(s.rosterCount!=null) el('rosterCount').value=s.rosterCount;
    if(s.listRows!=null) el('listRows').value=s.listRows;
    if(el('showLogo')){
        el('showLogo').checked = s.showLogo!==false;
        if(el('pLogo')) el('pLogo').style.display = el('showLogo').checked ? '' : 'none';
    }
    rows=Array.isArray(s.rows)?s.rows.map(function(r){ return Object.assign(blankRow(), r); }):[];
    rosterCells=s.rosterCells||{};
    saturdayPlan=(s.saturday && typeof s.saturday==='object')?s.saturday:{first:'',free:{}};
    if(!saturdayPlan.free) saturdayPlan.free={};
    el('satFirst').value=saturdayPlan.first||'';
    syncLayoutUI();                                   // toggles panels without wiping loaded data
    if(s.titleTouched) el('title').dataset.touched='1'; else delete el('title').dataset.touched;
    el('title').value=s.title||'';
    renderManageSaturdays();
    if(!isBlankGrid()) renderEditor();
    renderSheet();
}
function flashSaved(){
    var l=el('saveBtnLabel'), fresh=currentDesignId?'Save changes':'Save';
    l.textContent='Saved ✓';
    setTimeout(function(){ l.textContent=fresh; }, 1400);
}
function _designMarkSaved(){
    el('newBtn').style.display='';
    el('saveBtnLabel').textContent='Save changes';
}
function saveDesign(){
    var name=(el('saveName').value||'').trim();
    if(!name){ alert('Give the timetable a name first.'); el('saveName').focus(); return; }
    var body={ name:name, layout:el('layout').value, data:collectState() };
    if(currentDesignId) body.id=currentDesignId;
    fetch(URL_SAVE, { method:'POST', credentials:'same-origin',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) })
      .then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
      .then(function(res){
        if(!res.ok){ alert((res.j&&res.j.error)||'Could not save the timetable.'); return; }
        currentDesignId=res.j.id; _designMarkSaved(); flashSaved(); loadSavedList(true);
      }).catch(function(){ alert('Network error while saving.'); });
}
function newDesign(){
    currentDesignId=null; el('saveName').value='';
    el('newBtn').style.display='none'; el('saveBtnLabel').textContent='Save';
}
function toggleSaved(){
    var p=el('savedPanel');
    if(p.style.display==='none'){ p.style.display='block'; loadSavedList(); }
    else p.style.display='none';
}
function renderSavedList(list){
    el('savedCount').textContent=list.length;
    if(!list.length){ el('savedPanel').innerHTML='<div class="saved-empty">No saved timetables yet. Give one a name and click Save.</div>'; return; }
    el('savedPanel').innerHTML=list.map(function(d){
        return '<div class="saved-item">'
             + '<div class="s-name">'+esc(d.name)+'<small>'+esc(labelForLayout(d.layout))+' · updated '+esc(d.updated_at)+'</small></div>'
             + '<div class="s-actions">'
             + '<button class="btn btn-sm btn-primary" data-call="loadDesign" data-args="'+d.id+'"><i class="fas fa-folder-open"></i> Load</button>'
             + '<button class="btn btn-sm btn-secondary" title="Duplicate" data-call="dupDesign" data-args="'+d.id+'"><i class="fas fa-copy"></i></button>'
             + '<button class="btn btn-sm btn-light" title="Delete" data-call="deleteDesign" data-args="'+d.id+'"><i class="fas fa-trash"></i></button>'
             + '</div></div>';
    }).join('');
}
function loadSavedList(silent){
    fetch(URL_LIST, { credentials:'same-origin', headers:{'X-Requested-With':'fetch'} })
      .then(function(r){ return r.json(); })
      .then(renderSavedList)
      .catch(function(){ if(!silent) el('savedPanel').innerHTML='<div class="saved-empty">Could not load saved timetables.</div>'; });
}
function _fetchDesign(id){
    return fetch(URL_LOAD+id, { credentials:'same-origin', headers:{'X-Requested-With':'fetch'} })
      .then(function(r){ return r.json(); });
}
function _parseData(d){ try{ return JSON.parse(d.data||'{}'); }catch(e){ return null; } }
function loadDesign(id){
    _fetchDesign(id).then(function(d){
        if(d.error){ alert('Could not load that timetable.'); return; }
        currentDesignId=d.id; el('saveName').value=d.name||''; _designMarkSaved();
        applyState(_parseData(d));
        el('savedPanel').style.display='none';
        window.scrollTo({ top:0, behavior:'smooth' });
    }).catch(function(){ alert('Network error while loading.'); });
}
function dupDesign(id){
    _fetchDesign(id).then(function(d){
        if(d.error){ alert('Could not load that timetable.'); return; }
        newDesign(); el('saveName').value=(d.name||'Timetable')+' (copy)';
        applyState(_parseData(d));
        el('savedPanel').style.display='none';
        window.scrollTo({ top:0, behavior:'smooth' });
    }).catch(function(){ alert('Network error while loading.'); });
}
function deleteDesign(id){
    if(!confirm('Delete this saved timetable? This cannot be undone.')) return;
    fetch(URL_DEL+id, { method:'POST', credentials:'same-origin' })
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(j.error){ alert('Could not delete that timetable.'); return; }
        if(String(currentDesignId)===String(id)) newDesign();
        loadSavedList();
      }).catch(function(){ alert('Network error while deleting.'); });
}

// ---------- "Timeline" theme ----------
// A dated, editorial layout for the Saturday / Holiday grids: a timeline of
// dates down the left, period times across the top (with any gap between two
// periods shown as a break), one line per Class/Stream, subjects as cards with
// a colour edge per subject, a "Next" marker on the coming date and a subject
// key at the foot. Other layouts keep their tables, restyled by the theme CSS.
var TL_COLOURS = ['#2f54eb','#e8590c','#0ca678','#ae3ec9','#e03131','#1098ad','#f08c00','#7048e8',
                  '#37b24d','#d6336c','#495057','#1c7ed6','#a16207','#099268','#c2255c','#74b816'];
var TL_MON = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
function isTimeline(){ return el('theme').value==='timeline'; }
function tlUsesTimeline(){
    return (isTimeline() || isTickets() || isGazette() || isSwiss() || isNotebook() || isBoard() || isQuiet() || isInline()) && !isBlankGrid() && layout().mode==='grid' && el('orient').value!=='cols';
}
function tlTodayISO(){ var d=new Date(); return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2); }
// Shared by the poster themes. A run of 2+ periods that is the same lesson for
// EVERY class/stream that day (e.g. "Skill Acquisition" 10:00–1:00 for SS1–SS3)
// is drawn once, as one band across all the streams, instead of being repeated
// in each narrow column where a long name would overflow.
function tlRuns(d, gs, periods){
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var cell=function(g,i){ return sig(d.cells[g+'§'+periods[i].k]||[]); };
    var res=[];
    for(var i=0;i<periods.length;){
        var s0=cell(gs[0],i);
        var all=!!s0 && gs.every(function(g){ return cell(g,i)===s0; });
        if(!all){ i++; continue; }
        var j=i+1;
        while(j<periods.length && gs.every(function(g){ return cell(g,j)===s0; })) j++;
        if(j-i>=2) res[i]=j;
        i=j;
    }
    return res;
}
function tlRunInfo(d, gs, periods, i, j){
    var r=(d.cells[gs[0]+'§'+periods[i].k]||[])[0]||{};
    var end=periods[j-1].end||'';
    return {r:r, n:j-i, from:fmtT(periods[i].start), to:end?clock12(end,true):'', who:gs.length>1?('All '+(isSaturdayLayout()?'streams':'classes')):''};
}
// Subject text that may break after "/" (BIO/CRS, CHEM/GOVT) instead of overflowing.
function tlSubj(t){ return esc(t||'—').replace(/\//g,'/<wbr>'); }

function tlModel(){
    var pmap={}, periods=[];
    rows.forEach(function(r){ if(r.time && !isAll(r.group)){ var k=periodKey(r);
        if(!pmap[k]){ pmap[k]={k:k,start:r.time,end:r.dur?addMinutes(r.time,r.dur):''}; periods.push(pmap[k]); } } });
    periods.sort(function(a,b){ return a.start.localeCompare(b.start); });
    // subject colours, in first-seen order; teachers per subject for the key
    var colour={}, teach={}, ci=0;
    rows.forEach(function(r){ var sj=(r.subject||'').trim(); if(!sj || isAll(r.group)) return;
        if(!(sj in colour)){ colour[sj]=TL_COLOURS[ci++ % TL_COLOURS.length]; teach[sj]=[]; }
        // "Miss Gertrude" and "Miss. Gertrude" are the same person: compare
        // without dots, extra spaces or case so the key lists them once.
        var t=(r.teacher||'').trim(), nk=function(x){ return x.toLowerCase().replace(/[.\s]+/g,' ').trim(); };
        if(t && !teach[sj].some(function(x){ return nk(x)===nk(t); })) teach[sj].push(t); });
    var anyGroup = rows.some(function(r){ return (r.group||'').trim() && !isAll(r.group); });
    var dmap={}, order=[];
    rows.forEach(function(r){
        var date=r.date||'', day=(date?dayFromDate(date):'') || (r.day||'').trim() || '—', key=date||day;
        if(!dmap[key]){ dmap[key]={day:day,date:date,label:r.daylabel||'',
            sort:(parseDateAny(date)?parseDateAny(date).iso:('zz'+('0'+dayRank(day)).slice(-2))),
            groups:[],gset:{},cells:{},banners:[]}; order.push(key); }
        var d=dmap[key];
        if(isAll(r.group)){ if(r.subject||r.teacher) d.banners.push(r); return; }
        var g=(r.group||'').trim(); if(!(g in d.gset)){ d.gset[g]=1; d.groups.push(g); }
        if(r.time){ var ck=g+'§'+periodKey(r); (d.cells[ck]=d.cells[ck]||[]).push(r); }
    });
    // Saturday plan: lesson-free Saturdays inside the term show as "No class".
    if(isSaturdayLayout()){
        var info=computeSaturdayDates(), lastIso='';
        order.forEach(function(k){ if(dmap[k].sort>lastIso && dmap[k].sort.indexOf('zz')) lastIso=dmap[k].sort; });
        info.saturdays.forEach(function(sv){ if(sv.free && !dmap[sv.iso] && (_pageKeys ? _pageKeys[sv.iso] : (lastIso && sv.iso<lastIso))){
            dmap[sv.iso]={off:true,date:sv.iso,sort:sv.iso,groups:[],cells:{},banners:[]}; order.push(sv.iso); } });
    }
    order.sort(function(a,b){ return String(dmap[a].sort).localeCompare(String(dmap[b].sort)); });
    var today=tlTodayISO(), next='';
    order.forEach(function(k){ var d=dmap[k]; if(!next && !d.off && d.date && toISO(d.date)>=today) next=k; });
    var groupsAll=[]; rows.forEach(function(r){ var g=(r.group||'').trim(); if(g && !isAll(r.group) && groupsAll.indexOf(g)<0) groupsAll.push(g); });
    return {periods:periods, colour:colour, teach:teach, anyGroup:anyGroup, dmap:dmap, order:order, next:next, groupsAll:groupsAll};
}
function tlPrinted(){ var now=new Date(); var m=TL_MON[now.getMonth()];
    return now.getDate()+' '+m.charAt(0)+m.slice(1).toLowerCase()+' '+now.getFullYear(); }
function renderTimelineSheet(){
    var md=tlModel(), periods=md.periods, colour=md.colour, teach=md.teach, anyGroup=md.anyGroup,
        dmap=md.dmap, order=md.order, groupsAll=md.groupsAll;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    // Column tracks: a period is 1fr; a gap before the next period is a thin break track.
    var tracks=[], pcol={}, col=(anyGroup?2:1), heads='';
    periods.forEach(function(pd, i){
        if(i>0 && periods[i-1].end && periods[i-1].end < pd.start){
            tracks.push('1.1em');
            heads+='<div class="tl-br" style="grid-column:'+col+'"><span>Break</span></div>';
            pd.brk=col; col++;
        }
        tracks.push('minmax(0,1fr)'); pcol[pd.k]=col;
        // Exports drop am/pm: at readable sizes "11:30am" runs into the next column.
        heads+='<div class="tl-ph" style="grid-column:'+col+'"><b>'+esc(el('sheet').classList.contains('exporting') ? fmtT(pd.start) : clock12(pd.start,true))+'</b>'
             + (pd.end?'<small>to '+esc(clock12(pd.end,true))+'</small>':'')+'</div>';
        col++;
    });
    var tmpl=(anyGroup?'var(--tl-gw,3.4em) ':'')+tracks.join(' ');
    var lastCol=col;
    var breaks=periods.filter(function(pd){ return pd.brk; }).map(function(pd){ return pd.brk; });
    var next=md.next;
    var card=function(r, span, n){
        var sj=(r.subject||'').trim(), c=colour[sj]||'#a8a29e';
        var note=[(r.teacher||'').trim(), n>1?(n+' periods'):''].filter(Boolean).join(' · ');
        return '<div class="tl-c" style="--a:'+c+';grid-column:'+span+'">'
             + '<b>'+esc(sj||'—')+'</b>'
             + (note?'<small>'+esc(note)+'</small>':'')+'</div>';
    };
    var parts=[], n=0;
    order.forEach(function(key){
        var d=dmap[key], p=parseDateAny(d.date);
        var big=p?('0'+p.d).slice(-2):esc((d.day||'').slice(0,3));
        var mon=p?TL_MON[p.m-1]:'';
        if(d.off){
            parts[parts.length]='<div class="tl-wk off"><div class="tl-dt"><b>'+big+'</b><span>'+mon+'</span></div><div class="tl-rail"><i></i></div>'
                + '<div class="tl-off">No class this Saturday</div></div>';
            return;
        }
        n++;
        var sub = d.label || (p ? d.day.slice(0,3) : '');
        var isNext = key===next;
        var lines='';
        (anyGroup ? d.groups : ['']).forEach(function(g){
            var l='', gi=0;
            if(anyGroup) l+='<span class="tl-g" style="grid-column:1">'+esc(g||'—')+'</span>';
            breaks.forEach(function(b){ l+='<span class="tl-bk" style="grid-column:'+b+'"></span>'; });
            for(var i=0;i<periods.length;){
                var arr=d.cells[g+'§'+periods[i].k]||[], sig=arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§');
                var j=i+1;
                // merge a run of identical consecutive periods (no break between them)
                while(sig && j<periods.length && !periods[j].brk &&
                      (d.cells[g+'§'+periods[j].k]||[]).map(function(r){ return r.subject+'|'+r.teacher; }).join('§')===sig) j++;
                var from=pcol[periods[i].k], to=pcol[periods[j-1].k]+1;
                if(!arr.length) l+='<div class="tl-c empty" style="grid-column:'+from+' / '+to+'"></div>';
                else if(arr.length===1) l+=card(arr[0], from+' / '+to, j-i);
                else l+='<div class="tl-multi" style="grid-column:'+from+' / '+to+'">'+arr.map(function(r){ return card(r,'auto'); }).join('')+'</div>';
                i=j;
            }
            lines+='<div class="tl-ln" style="grid-template-columns:'+tmpl+'">'+l+'</div>';
        });
        d.banners.forEach(function(b){
            lines+='<div class="tl-ln" style="grid-template-columns:'+tmpl+'"><div class="tl-ban" style="grid-column:1 / '+lastCol+'"><b>'
                 + esc(b.subject||'')+'</b>'+((b.teacher||'').trim()?'<small>'+esc(b.teacher)+'</small>':'')+'</div></div>';
        });
        parts[parts.length]='<div class="tl-wk'+(isNext?' nxt':'')+'"><div class="tl-dt"><b>'+big+'</b>'
            + (mon?'<span>'+mon+'</span>':'')
            + (isNext?'<em class="nx">NEXT</em>':(sub?'<em>'+esc(sub.replace(/^Week /,'Wk '))+'</em>':''))
            + '</div><div class="tl-rail"><i></i></div><div class="tl-body">'+lines+'</div></div>';
    });
    var keyHtml=Object.keys(colour).map(function(sj){
        return '<span style="--a:'+colour[sj]+'"><i></i><b>'+esc(sj)+'</b><em>'+esc(teach[sj].join(', '))+'</em></span>'; }).join('');
    // Two halves, each with its own time row: stacked on portrait (the second
    // time row hidden), side by side on a landscape page — so 8+ dates fit
    // an A4 landscape sheet without shrinking.
    var hd='<div class="tl-hd"><span></span><span></span><div class="tl-ln" style="grid-template-columns:'+tmpl+'">'+heads+'</div></div>';
    var cut=Math.ceil(parts.length/2);
    el('pBody').innerHTML='<div class="tl">'
        + '<div class="tl-split"><div class="tl-half">'+hd+'<div class="tl-list">'+parts.slice(0,cut).join('')+'</div></div>'
        + (parts.length>cut?'<div class="tl-half">'+hd+'<div class="tl-list">'+parts.slice(cut).join('')+'</div></div>':'')+'</div>'
        + (keyHtml?'<div class="tl-key">'+keyHtml+'</div>':'')
        + '<div class="tl-foot"><span>'+(groupsAll.length?esc(groupsAll.join(' · ')):'')+'</span><span>Printed '
        + tlPrinted()+'</span></div>'
        + '</div>';
}

// ---------- "Tickets" theme ----------
// Each date is a cut-out ticket: a stub with the week / date on the left, a
// perforated tear line, then one column per Class/Stream listing every lesson
// as time · coloured dot · subject · teacher, with breaks in place, double
// periods marked ×2, the coming date in gold and lesson-free Saturdays greyed.
function isTickets(){ return el('theme').value==='tickets'; }
function renderTicketsSheet(){
    var md=tlModel(), periods=md.periods, colour=md.colour, dmap=md.dmap, order=md.order;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var line=function(time, r, n){
        var sj=(r.subject||'').trim(), c=colour[sj]||'#8d99ae';
        return '<li style="--c:'+c+'"><time>'+esc(time)+'</time><i></i><b>'+tlSubj(sj)
             + (n>1?'<em>×'+n+'</em>':'')+'</b>'+((r.teacher||'').trim()?'<small>'+esc(r.teacher)+'</small>':'')+'</li>';
    };
    var n=0, html='', offPending=[], offAll=[];
    order.forEach(function(key){
        var d=dmap[key], p=parseDateAny(d.date);
        var big=p?('0'+p.d).slice(-2):esc((d.day||'').slice(0,3));
        var mon=p?TL_MON[p.m-1]:'';
        var wkNo=(d.label||'').match(/^Week\s+(\d+)/i);
        // A lesson-free Saturday is not a whole ticket: it becomes a small note
        // on the next ticket (or the previous one, if it falls at the end).
        if(d.off){ offPending.push(p ? (p.d+' '+mon.charAt(0)+mon.slice(1).toLowerCase()) : big); offAll.push(offPending[offPending.length-1]); return; }
        n++;
        var isNext = key===md.next;
        var stubTop = wkNo ? '<small>WEEK</small><span class="tk-wn">'+('0'+wkNo[1]).slice(-2)+'</span>'
                           : (p ? '<small>'+esc(d.day.toUpperCase())+'</small>' : '');
        var gsT = md.anyGroup ? d.groups : [''];
        var runs = gsT.length ? tlRuns(d, gsT, periods) : [];
        var segs=[], a0=0;
        for(var si=0; si<periods.length;){
            if(runs[si]){ if(si>a0) segs.push([a0,si]); segs.push(['run',si,runs[si]]); si=runs[si]; a0=si; }
            else si++;
        }
        if(a0<periods.length) segs.push([a0,periods.length]);
        var lanesFor=function(from, to, withHead){
          var lanes='';
          gsT.forEach(function(g){
            var items='';
            for(var i=from;i<to;){
                var arr=d.cells[g+'§'+periods[i].k]||[], sg=sig(arr), j=i+1;
                while(sg && j<to && sig(d.cells[g+'§'+periods[j].k]||[])===sg) j++;
                if(i>from && periods[i].brk===undefined && periods[i-1].end && periods[i-1].end<periods[i].start){
                    var mins=(function(a,b){ var x=a.split(':'),y=b.split(':'); return (+y[0]*60+ +y[1])-(+x[0]*60+ +x[1]); })(periods[i-1].end, periods[i].start);
                    items+='<li class="tk-brk"><time>'+esc(fmtT(periods[i-1].end))+'</time><span>Break · '+mins+' min</span></li>';
                }
                if(arr.length) arr.forEach(function(r){ items+=line(fmtT(periods[i].start), r, j-i); });
                else items+='<li class="tk-free"><time>'+esc(fmtT(periods[i].start))+'</time><span>Free</span></li>';
                // a break that falls inside a merged run is still shown after it
                for(var q=i+1;q<j;q++){ if(periods[q-1].end && periods[q-1].end<periods[q].start){
                    items+='<li class="tk-brk"><time>'+esc(fmtT(periods[q-1].end))+'</time><span>Break</span></li>'; } }
                i=j;
            }
            lanes+='<div class="tk-lane">'+(md.anyGroup && withHead?'<h4>'+esc(g||'—')+'</h4>':'')+'<ol>'+items+'</ol></div>';
          });
          return lanes;
        };
        var lanes='';
        segs.forEach(function(sg, k){
            if(sg[0]==='run'){
                var ri=tlRunInfo(d,gsT,periods,sg[1],sg[2]), r=ri.r, c=colour[(r.subject||'').trim()]||'#8d99ae';
                if(sg[1]>0 && periods[sg[1]-1].end && periods[sg[1]-1].end<periods[sg[1]].start)
                    lanes+='<div class="tk-sbrk">Break '+esc(fmtT(periods[sg[1]-1].end))+'</div>';
                lanes+='<div class="tk-band" style="--c:'+c+'"><time>'+esc(ri.from)+(ri.to?'–'+esc(ri.to):'')+'</time><i></i><b>'+tlSubj(r.subject)+'<em>×'+ri.n+'</em></b>'
                    + '<small>'+esc([ri.who,(r.teacher||'').trim()].filter(Boolean).join(' · '))+'</small></div>';
            } else {
                if(k>0 && periods[sg[0]-1] && periods[sg[0]-1].end && periods[sg[0]-1].end<periods[sg[0]].start)
                    lanes+='<div class="tk-sbrk">Break '+esc(fmtT(periods[sg[0]-1].end))+'</div>';
                lanes+='<div class="tk-lanes'+(k?' cont':'')+'">'+lanesFor(sg[0],sg[1],k===0)+'</div>';
            }
        });
        var bans=d.banners.map(function(b){ return '<div class="tk-ban"><b>'+esc(b.subject||'')+'</b>'
            + ((b.teacher||'').trim()?'<small>'+esc(b.teacher)+'</small>':'')+'</div>'; }).join('');
        var note = offPending.length ? '<div class="tk-note">No class on Sat '+esc(offPending.join(', '))+' · classes resume here</div>' : '';
        offPending=[];
        html+='<article class="tk'+(isNext?' nxt':'')+'"><div class="tk-stub">'+stubTop
            + '<div class="tk-dd"><b>'+big+'</b>'+(mon?'<span>'+mon+'</span>':'')+'</div>'
            + (p && wkNo ? '<small class="tk-day">'+esc(d.day.toUpperCase())+'</small>' : '')
            + (isNext?'<span class="tk-next">NEXT CLASS</span>':'')+'</div><div class="tk-perf"></div>'
            + '<div class="tk-main">'+note+lanes+bans+'</div></article>';
    });
    if(offPending.length && html){   // lesson-free Saturdays after the last class
        var i=html.lastIndexOf('<div class="tk-main">')+'<div class="tk-main">'.length;
        html=html.slice(0,i)+'<div class="tk-note">No class on Sat '+esc(offPending.join(', '))+' (after this one)</div>'+html.slice(i);
    }
    var keyHtml=Object.keys(colour).map(function(sj){ return '<span style="--c:'+colour[sj]+'"><i></i>'+esc(sj)+'</span>'; }).join('');
    el('pBody').innerHTML='<div class="tl tkx"><div class="tl-list tk-grid">'+html+'</div>'
        + '<div class="tk-foot"><div class="tk-key">'+keyHtml+'</div><div class="tk-p">'+(offAll.length?'No class: Sat '+esc(offAll.join(', '))+'<br>':'')+'×2 = double period<br>Printed '+tlPrinted()+'</div></div></div>';
}

// ---------- "Gazette" theme ----------
// A school-newspaper front page: the coming date is the lead story (a large
// table for every class/stream), every other date is a short "article" with
// its own small table, lesson-free Saturdays get a one-line piece, and a
// subject → teacher directory fills the lead column. Black ink + one red accent.
function isGazette(){ return el('theme').value==='gazette'; }
var GZ_MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
function gzDate(d){ var p=parseDateAny(d.date); return p ? (p.d+' '+GZ_MONTHS[p.m-1]) : (d.label||d.day||''); }
function renderGazetteSheet(){
    var md=tlModel(), periods=md.periods, dmap=md.dmap, order=md.order, teach=md.teach;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var groups = md.anyGroup ? md.groupsAll : [''];
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var table=function(d, big){
        if(!(d.groups||[]).length && d.banners.length){
            return '<div class="gz-event">'+d.banners.map(function(b){ return '<b>'+esc(b.subject||'')+'</b>'
                + ((b.teacher||'').trim()?'<small>'+esc(b.teacher)+'</small>':''); }).join('')+'</div>';
        }
        var gs = md.anyGroup ? groups.filter(function(g){ return d.gset && (g in d.gset); }) : [''];
        if(!gs.length) gs=[''];
        var head='<tr><th></th>'+gs.map(function(g){ return '<th>'+esc(g||'Lesson')+'</th>'; }).join('')+'</tr>';
        var body='', runs=tlRuns(d,gs,periods), skip={};
        periods.forEach(function(pd, i){
            if(skip[i]) return;
            if(runs[i]){
                for(var q=i+1;q<runs[i];q++) skip[q]=1;
                var ri=tlRunInfo(d,gs,periods,i,runs[i]);
                body+='<tr class="gz-span"><td class="gz-t">'+esc(ri.from)+'</td><td colspan="'+gs.length+'"><b>'+tlSubj(ri.r.subject)+'</b>'
                    + ' <i>('+ri.n+' periods'+(ri.to?', until '+esc(ri.to):'')+')</i>'
                    + ((ri.r.teacher||'').trim()||ri.who?'<small>'+esc([ri.who,(ri.r.teacher||'').trim()].filter(Boolean).join(' · '))+'</small>':'')+'</td></tr>';
                return;
            }
            if(i>0 && periods[i-1].end && periods[i-1].end<pd.start)
                body+='<tr class="gz-br"><td>'+esc(fmtT(periods[i-1].end))+'</td><td colspan="'+gs.length+'">— Break —</td></tr>';
            var cells='';
            gs.forEach(function(g){
                var arr=d.cells[g+'§'+pd.k]||[], sg=sig(arr);
                var prev=i>0?sig(d.cells[g+'§'+periods[i-1].k]||[]):'';
                if(sg && sg===prev){ cells+='<td class="gz-cont">″</td>'; return; }
                var n=1; while(sg && i+n<periods.length && sig(d.cells[g+'§'+periods[i+n].k]||[])===sg) n++;
                cells+='<td>'+(arr.length?arr.map(function(r){
                    return '<b>'+tlSubj(r.subject)+'</b>'+(n>1?' <i>('+(n===2?'double':n+' periods')+')</i>':'')
                         + ((r.teacher||'').trim()?'<small>'+esc(r.teacher)+'</small>':''); }).join('<br>'):'<span class="gz-free">Free</span>')+'</td>';
            });
            body+='<tr><td class="gz-t">'+esc(fmtT(pd.start))+'</td>'+cells+'</tr>';
        });
        d.banners.forEach(function(b){
            body+='<tr class="gz-ban"><td colspan="'+(gs.length+1)+'"><b>'+esc(b.subject||'')+'</b>'
                + ((b.teacher||'').trim()?' <small>'+esc(b.teacher)+'</small>':'')+'</td></tr>';
        });
        return '<table class="gz-tt'+(big?' big':'')+' g'+Math.min(gs.length,4)+'"><thead>'+head+'</thead><tbody>'+body+'</tbody></table>';
    };
    var real=order.filter(function(k){ return !dmap[k].off; });
    // Multi-page export: only the first page leads with a feature date.
    var leadKey = _laterPage ? null : (md.next || real[0]);
    var weekOf=function(d){ var m=(d.label||'').match(/^Week\s+(\d+)/i); return m?('Week '+m[1]):(d.date?d.day:''); };
    var lead=leadKey ? dmap[leadKey] : null;
    var leadHtml=!lead ? '' : '<section class="gz-lead"><div class="gz-kick">'+(md.next?'Next class':'First class')+(weekOf(lead)?' · '+esc(weekOf(lead)):'')+'</div>'
        + '<h2>'+esc(lead.date?(dayFromDate(lead.date)+', '+gzDate(lead)):gzDate(lead))+'</h2>'
        + table(lead, true);
    var dirKeys=Object.keys(teach).filter(function(sj){ return teach[sj].length; });
    if(lead && dirKeys.length){
        leadHtml+='<div class="gz-box"><h4>Teachers</h4><ul>'+dirKeys.map(function(sj){
            return '<li><b>'+esc(sj)+'</b><span>'+esc(teach[sj].join(', '))+'</span></li>'; }).join('')+'</ul></div>';
    }
    if(lead) leadHtml+='</section>';
    else leadHtml='';
    // Lesson-free Saturdays are a one-line note on the next class (not a whole
    // article), plus a mention in the dateline strip.
    var arts='', offPending=[], offAll=[], leadNote='';
    var noteOf=function(list, after){ return '<p class="gz-note">No class on Saturday '+esc(list.join(', '))+(after?' (after this class)':'')+'</p>'; };
    order.forEach(function(k){
        var d=dmap[k];
        if(d.off){ offPending.push(gzDate(d)); offAll.push(gzDate(d).replace(/(\d+) (\w{3})\w*/,'$1 $2')); return; }
        var note = offPending.length ? noteOf(offPending) : '';
        offPending=[];
        if(k===leadKey){ leadNote=note; return; }
        arts+='<article><h3>'+(weekOf(d)?'<span>'+esc(weekOf(d))+'</span>':'')+esc(gzDate(d))+'</h3>'+note+table(d,false)+'</article>';
    });
    if(offPending.length){
        var at=arts.lastIndexOf('</h3>');
        if(at>=0) arts=arts.slice(0,at+5)+noteOf(offPending,true)+arts.slice(at+5); else leadNote+=noteOf(offPending,true);
    }
    if(leadNote && lead) leadHtml=leadHtml.replace('</h2>','</h2>'+leadNote);
    else if(leadNote) arts=leadNote+arts;
    var dates=real.map(function(k){ return dmap[k]; }).filter(function(d){ return d.date; });
    var range = dates.length ? (gzDate(dates[0]).replace(/(\d+) (\w{3})\w*/,'$1 $2')+' – '+gzDate(dates[dates.length-1]).replace(/(\d+) (\w{3})\w*/,'$1 $2')) : '';
    var unit = isSaturdayLayout() ? 'Saturday' : 'day';
    var strip='<div class="gz-dl"><span>'+real.length+' '+unit+(real.length===1?'':'s')+(range?' · '+esc(range):'')
        + (offAll.length?' · no class '+esc(offAll.join(', ')):'')+'</span>'
        + (md.next?'<b>Next class: '+esc(gzDate(dmap[md.next]))+'</b>':'<span></span>')
        + '<span>Printed '+tlPrinted()+'</span></div>';
    var marks=[];
    if(/″/.test(arts+leadHtml)) marks.push('″ = continues from the period above');
    if(/\(double\)/.test(arts+leadHtml)) marks.push('(double) = two periods');
    el('pBody').innerHTML='<div class="tl gz">'+strip+'<div class="gz-body">'+leadHtml
        + '<div class="tl-list gz-cols">'+arts+'</div></div>'
        + '<div class="gz-foot"><span>'+esc(marks.join(' · '))+'</span><span>'+esc(el('school').value||'')+'</span></div></div>';
}

// ---------- "Swiss" theme ----------
// International-typographic poster: huge title, an 8-segment progress bar
// (done / next / to go), each date a ruled block with a big date, an outlined
// week numeral behind it and a precise per-stream table; one red-orange accent.
function isSwiss(){ return el('theme').value==='swiss'; }
function renderSwissSheet(){
    var md=tlModel(), periods=md.periods, dmap=md.dmap, order=md.order, teach=md.teach;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var real=order.filter(function(k){ return !dmap[k].off; });
    var nextIdx=md.next?real.indexOf(md.next):-1;
    var pad=function(n){ return ('0'+n).slice(-2); };
    var prog=real.map(function(k,i){ return '<i class="'+(nextIdx<0?'':(i<nextIdx?'d':(i===nextIdx?'n':'')))+'"><span>'+pad(i+1)+'</span></i>'; }).join('');
    var done=nextIdx<0?0:nextIdx;
    var sum = nextIdx<0 ? real.length+' '+(isSaturdayLayout()?'Saturdays':'days')
            : '<b>'+done+'</b> done · <b class="sw-a">'+(isSaturdayLayout()?'week ':'day ')+pad(nextIdx+1)+'</b> next · <b>'+(real.length-nextIdx-1)+'</b> to go';
    var table=function(d){
        if(!(d.groups||[]).length && d.banners.length){
            return '<div class="sw-ev">'+d.banners.map(function(b){ return '<b>'+esc(b.subject||'')+'</b>'+((b.teacher||'').trim()?'<small>'+esc(b.teacher)+'</small>':''); }).join('')+'</div>';
        }
        var gs = md.anyGroup ? md.groupsAll.filter(function(g){ return d.gset && (g in d.gset); }) : [''];
        if(!gs.length) gs=[''];
        // Exports lift the small times to a readable size: give them room.
        var tw=el('sheet').classList.contains('exporting') ? 22 : 15;
        var w=Math.floor((100-tw)/gs.length);
        var cols='<colgroup><col style="width:'+tw+'%">'+gs.map(function(){ return '<col style="width:'+w+'%">'; }).join('')+'</colgroup>';
        var head='<tr><th></th>'+gs.map(function(g){ return '<th>'+esc(g||'Lesson')+'</th>'; }).join('')+'</tr>';
        var body='', runs=tlRuns(d,gs,periods), skip={};
        periods.forEach(function(pd,i){
            if(skip[i]) return;
            if(runs[i]){
                for(var q=i+1;q<runs[i];q++) skip[q]=1;
                var ri=tlRunInfo(d,gs,periods,i,runs[i]);
                body+='<tr class="sw-span"><td class="sw-t">'+esc(ri.from)+'</td><td colspan="'+gs.length+'"><b>'+tlSubj(ri.r.subject)+'</b><sup>'+ri.n+'×</sup>'
                    + '<small>'+esc([ri.to?'until '+ri.to:'', ri.who, (ri.r.teacher||'').trim()].filter(Boolean).join(' · '))+'</small></td></tr>';
                return;
            }
            if(i>0 && periods[i-1].end && periods[i-1].end<pd.start)
                body+='<tr class="sw-brk"><td>'+esc(fmtT(periods[i-1].end))+'</td><td colspan="'+gs.length+'"><span>break</span></td></tr>';
            var cells='';
            gs.forEach(function(g){
                var arr=d.cells[g+'§'+pd.k]||[], sg=sig(arr);
                var prev=i>0?sig(d.cells[g+'§'+periods[i-1].k]||[]):'';
                if(sg && sg===prev){ cells+='<td class="sw-cont">↓</td>'; return; }
                var n=1; while(sg && i+n<periods.length && sig(d.cells[g+'§'+periods[i+n].k]||[])===sg) n++;
                cells+='<td>'+(arr.length?arr.map(function(r){ return '<b>'+tlSubj(r.subject)+'</b>'+(n>1?'<sup>'+n+'×</sup>':'')
                    + ((r.teacher||'').trim()?'<small>'+esc(r.teacher)+'</small>':''); }).join(''):'<span class="sw-free">—</span>')+'</td>';
            });
            body+='<tr><td class="sw-t">'+esc(fmtT(pd.start))+'</td>'+cells+'</tr>';
        });
        d.banners.forEach(function(b){ body+='<tr class="sw-ban"><td colspan="'+(gs.length+1)+'"><b>'+esc(b.subject||'')+'</b></td></tr>'; });
        return '<table>'+cols+'<thead>'+head+'</thead><tbody>'+body+'</tbody></table>';
    };
    var html='', offPending=[], offAll=[], idx=0;
    order.forEach(function(k){
        var d=dmap[k], p=parseDateAny(d.date);
        var dd=p?gzDate(d).replace(/(\d+) (\w{3})\w*/,'$1 $2'):'';
        if(d.off){ offPending.push(dd||gzDate(d)); offAll.push(dd||gzDate(d)); return; }
        idx++;
        var i=real.indexOf(k);
        var cls='sw-wk'+(k===md.next?' nx':'')+(nextIdx>=0 && i<nextIdx?' past':'');
        var note=offPending.length?'<div class="sw-gap">No class '+(isSaturdayLayout()?'Sat ':'')+esc(offPending.join(', '))+'</div>':'';
        offPending=[];
        var big=p?pad(p.d):esc((d.day||'').slice(0,3));
        var mon=p?TL_MON[p.m-1]:'';
        var day=(p?d.day:'').toUpperCase();
        html+='<section class="'+cls+'"><div class="sw-num" aria-hidden="true">'+pad(idx)+'</div><header><span class="sw-d">'+big+'</span><span class="sw-m">'+mon
            + (day?'<br><i>'+esc(day)+'</i>':'')+'</span>'+(k===md.next?'<span class="sw-flag">Next class →</span>':'')+'</header>'+note+table(d)+'</section>';
    });
    if(offPending.length && html){
        var at=html.lastIndexOf('</header>')+9;
        html=html.slice(0,at)+'<div class="sw-gap">No class '+esc(offPending.join(', '))+' (after this)</div>'+html.slice(at);
    }
    var key=Object.keys(teach).filter(function(sj){ return teach[sj].length; }).map(function(sj){
        return '<span><b>'+esc(sj)+'</b>'+esc(teach[sj].join(', '))+'</span>'; }).join('');
    var marks=[];
    if(/<sup>/.test(html)) marks.push('2× double period');
    if(/sw-cont/.test(html)) marks.push('↓ continues');
    if(offAll.length) marks.push('no class '+offAll.join(', '));
    el('pBody').innerHTML='<div class="tl sw">'
        + '<div class="sw-prog">'+prog+'</div>'
        + '<div class="sw-leg"><span>'+sum+'</span><span>'+esc(marks.join(' · '))+'</span></div>'
        + '<div class="tl-list sw-grid">'+html+'</div>'
        + '<div class="sw-foot"><div class="sw-key">'+key+'</div><div class="sw-p">Printed<br>'+tlPrinted()+'</div></div></div>';
}

// ---------- "Exercise Book" theme ----------
// A page from a pupil's exercise book: ruled paper, red margin, punched holes,
// a filled-in cover label (the heading), coloured index tabs (one per date),
// each date a "Week N" entry written on the lines; finished weeks faded with a
// tick, the next class circled in marker with a sticky note.
var NB_TABS=['#e03131','#f08c00','#2f9e44','#1971c2','#7048e8','#c2255c','#0c8599','#5c940d','#e8590c','#495057'];
function isNotebook(){ return el('theme').value==='notebook'; }
function renderNotebookSheet(){
    var md=tlModel(), periods=md.periods, dmap=md.dmap, order=md.order;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var real=order.filter(function(k){ return !dmap[k].off; });
    var nextIdx=md.next?real.indexOf(md.next):-1;
    var block=function(d){
        if(!(d.groups||[]).length && d.banners.length){
            return '<div class="nb-ev">'+d.banners.map(function(b){ return '<b>'+esc(b.subject||'')+'</b>'+((b.teacher||'').trim()?'<small>'+esc(b.teacher)+'</small>':''); }).join('')+'</div>';
        }
        var gs = md.anyGroup ? md.groupsAll.filter(function(g){ return d.gset && (g in d.gset); }) : [''];
        if(!gs.length) gs=[''];
        // Exports lift small text (the times) to a readable size: give it room.
        var tmpl='grid-template-columns:'+(el('sheet').classList.contains('exporting')?'4.8em':'3.3em')+' repeat('+gs.length+',minmax(0,1fr))';
        var runs=tlRuns(d,gs,periods), skip={};
        var out='<div class="nb-r nb-h" style="'+tmpl+'"><span></span>'+gs.map(function(g){ return '<span>'+esc(g||'Lesson')+'</span>'; }).join('')+'</div>';
        periods.forEach(function(pd,i){
            if(skip[i]) return;
            if(runs[i]){
                for(var q=i+1;q<runs[i];q++) skip[q]=1;
                var ri=tlRunInfo(d,gs,periods,i,runs[i]);
                out+='<div class="nb-r nb-span" style="'+tmpl+'"><span class="nb-t">'+esc(ri.from)+'</span><div class="nb-c" style="grid-column:2 / -1"><b>'+tlSubj(ri.r.subject)+'</b><u>'+ri.n+' periods</u>'
                    + '<small>'+esc([ri.to?'until '+ri.to:'', ri.who, (ri.r.teacher||'').trim()].filter(Boolean).join(' · '))+'</small></div></div>';
                return;
            }
            if(i>0 && periods[i-1].end && periods[i-1].end<pd.start)
                out+='<div class="nb-r nb-brk" style="'+tmpl+'"><span>'+esc(fmtT(periods[i-1].end))+'</span><em style="grid-column:2 / -1">break</em></div>';
            var cells='';
            gs.forEach(function(g){
                var arr=d.cells[g+'§'+pd.k]||[], sg=sig(arr);
                var prev=i>0?sig(d.cells[g+'§'+periods[i-1].k]||[]):'';
                if(sg && sg===prev){ cells+='<div class="nb-c nb-cont">〃</div>'; return; }
                var n=1; while(sg && i+n<periods.length && sig(d.cells[g+'§'+periods[i+n].k]||[])===sg) n++;
                cells+='<div class="nb-c">'+(arr.length?arr.map(function(r){ return '<b>'+tlSubj(r.subject)+'</b>'+(n>1?'<u>'+(n===2?'double':n+' periods')+'</u>':'')
                    + ((r.teacher||'').trim()?'<small>'+esc(r.teacher)+'</small>':''); }).join(''):'<span class="nb-free">—</span>')+'</div>';
            });
            out+='<div class="nb-r" style="'+tmpl+'"><span class="nb-t">'+esc(fmtT(pd.start))+'</span>'+cells+'</div>';
        });
        d.banners.forEach(function(b){ out+='<div class="nb-r nb-ban"><b>'+esc(b.subject||'')+'</b></div>'; });
        return out;
    };
    var html='', offPending=[], offAll=[], idx=0;
    order.forEach(function(k){
        var d=dmap[k];
        if(d.off){ offPending.push(gzDate(d)); offAll.push(gzDate(d)); return; }
        var i=real.indexOf(k), col=NB_TABS[i % NB_TABS.length];
        idx++;
        var wk=(d.label||'').match(/^Week\s+(\d+)/i);
        var pill=wk?('Week '+wk[1]):(isSaturdayLayout()?('Week '+idx):('Day '+idx));
        var title=d.date?(dayFromDate(d.date)+', '+gzDate(d)):gzDate(d);
        var past=nextIdx>=0 && i<nextIdx, nx=k===md.next;
        var note=offPending.length?'<div class="nb-note">No class on '+esc(offPending.join(', '))+'</div>':'';
        offPending=[];
        html+='<section class="nb-wk'+(past?' past':'')+(nx?' nx':'')+'" style="--tab:'+col+'">'
            + (nx?'<div class="nb-postit">Next class!<br><b>'+esc(d.date?gzDate(d).replace(/(\d+) (\w{3})\w*/,'$1 $2'):title)+'</b></div>':'')
            + '<h3><span class="nb-pill">'+esc(pill)+'</span>'+esc(title)+(past?'<span class="nb-tick">✓</span>':'')+'</h3>'+note+block(d)+'</section>';
    });
    if(offPending.length && html){
        var at=html.lastIndexOf('</h3>')+5;
        html=html.slice(0,at)+'<div class="nb-note">No class on '+esc(offPending.join(', '))+' (after this)</div>'+html.slice(at);
    }
    var n=real.length||1;
    var tabs=real.map(function(k,i){
        return '<i class="'+(k===md.next?'on':'')+'" style="--tab:'+NB_TABS[i % NB_TABS.length]+';top:calc(14% + '+i+' * (80% / '+n+'));height:calc(80% / '+n+' - .35em)">'+(i+1)+'</i>'; }).join('');
    var marks=[];
    if(/nb-cont/.test(html)) marks.push('〃 continues from the period above');
    if(/<u>/.test(html)) marks.push('double = two periods');
    if(/nb-tick/.test(html)) marks.push('✓ done');
    var holes=''; for(var h=0;h<9;h++) holes+='<i style="top:'+(4+h*11.5)+'%"></i>';
    el('pBody').innerHTML='<div class="nb-holes">'+holes+'</div><div class="nb-tabs">'+tabs+'</div><div class="tl nb">'
        + '<div class="tl-list nb-grid">'+html+'</div>'
        + '<div class="nb-foot"><span>'+esc(marks.join(' · '))+'</span><span>Printed '+tlPrinted()+'</span></div></div>';
}

// ---------- "Board" theme ----------
// One light card per date, styled like a departures board: period times down
// the left, one column per class/stream, so a row is one moment and it is
// obvious every class is in a lesson at the same time. Lessons shared by all
// classes for 2+ periods become one block across the card; double periods are
// marked ×2 with ↓ in the next slot; past dates DONE, the coming date NEXT.
function isBoard(){ return el('theme').value==='board'; }
var BD_SHORT={'ENGLISH':'ENG','BIOLOGY':'BIO','PHYSICS':'PHY','CHEMISTRY':'CHEM','MATHEMATICS':'MATHS','ECONOMICS':'ECONS','GOVERNMENT':'GOVT',
  'LITERATURE':'LIT','GEOGRAPHY':'GEO','COMMERCE':'COMM','AGRICULTURE':'AGRIC','AGRIC SCIENCE':'AGRIC','CIVIC EDUCATION':'CIVIC','DATA PROCESSING':'DP'};
function renderBoardSheet(){
    var md=tlModel(), periods=md.periods, dmap=md.dmap, order=md.order;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var real=order.filter(function(k){ return !dmap[k].off; });
    var nextIdx=md.next?real.indexOf(md.next):-1;
    var gsAll = md.anyGroup ? md.groupsAll : [''];
    var tight = gsAll.length>2;
    var label=function(t){
        var up=(t||'').toUpperCase().trim();
        if(!tight) return esc(up).replace(/\//g,'/<wbr>');
        return up.split('/').map(function(p){ p=p.trim(); return esc(BD_SHORT[p]||p); }).join('/<wbr>');
    };
    var html='', offAll=[];
    order.forEach(function(k){
        var d=dmap[k], p=parseDateAny(d.date);
        if(d.off){ offAll.push(gzDate(d).replace(/(\d+) (\w{3})\w*/,'$1 $2')); return; }
        var i0=real.indexOf(k), st = k===md.next ? ' nx' : (nextIdx>=0 && i0<nextIdx ? ' past' : '');
        var head = p ? (d.day.slice(0,3)+' '+('0'+p.d).slice(-2)+' '+TL_MON[p.m-1]) : (d.label||d.day||'');
        var gs = md.anyGroup ? gsAll.filter(function(g){ return d.gset && (g in d.gset); }) : [''];
        var body='';
        if(!gs.length || (!(d.groups||[]).length && d.banners.length)){
            body = d.banners.map(function(b){ return '<div class="bd-all bd-ev"><b>'+esc(b.subject||'')+'</b>'
                + ((b.teacher||'').trim()?'<small>'+esc(b.teacher)+'</small>':'')+'</div>'; }).join('');
        } else {
            var tmpl='grid-template-columns:3.4em repeat('+gs.length+',minmax(0,1fr))';
            body+='<div class="bd-hd" style="'+tmpl+';--n:'+gs.length+'"><span>Time</span>'+gs.map(function(g){ return '<span>'+esc(g||'Lesson')+'</span>'; }).join('')+'</div>';
            var runs=tlRuns(d,gs,periods);
            for(var i=0;i<periods.length;){
                if(i>0 && periods[i-1].end && periods[i-1].end<periods[i].start)
                    body+='<div class="bd-br">Break</div>';
                if(runs[i]){
                    var ri=tlRunInfo(d,gs,periods,i,runs[i]);
                    body+='<div class="bd-rw bd-span" style="'+tmpl+';flex:'+ri.n+'"><b>'+esc(fmtT(periods[i].start))+'</b><span class="bd-all"><b>'+label(ri.r.subject)+'</b>'
                        + '<small>'+esc([ri.who, ri.from+(ri.to?' – '+ri.to:''), (ri.r.teacher||'').trim()].filter(Boolean).join(' · '))+'</small></span></div>';
                    i=runs[i]; continue;
                }
                var cells='';
                gs.forEach(function(g){
                    var arr=d.cells[g+'§'+periods[i].k]||[], sg=sig(arr);
                    var prev=i>0 && !(periods[i-1].end && periods[i-1].end<periods[i].start) ? sig(d.cells[g+'§'+periods[i-1].k]||[]) : '';
                    var nxt=i+1<periods.length && !(periods[i].end && periods[i].end<periods[i+1].start) ? sig(d.cells[g+'§'+periods[i+1].k]||[]) : '';
                    if(sg && sg===prev){ cells+='<span class="bd-c">↓</span>'; return; }
                    if(!arr.length){ cells+='<span class="bd-f">—</span>'; return; }
                    cells+='<span>'+arr.map(function(r){ return label(r.subject); }).join('<br>')+(sg && sg===nxt?'<em>×2</em>':'')
                        + (arr.length===1 && (arr[0].teacher||'').trim() && !tight?'<small>'+esc(arr[0].teacher)+'</small>':'')+'</span>';
                });
                body+='<div class="bd-rw" style="'+tmpl+'"><b>'+esc(fmtT(periods[i].start))+'</b>'+cells+'</div>';
                i++;
            }
            d.banners.forEach(function(b){ body+='<div class="bd-all bd-ev"><b>'+esc(b.subject||'')+'</b></div>'; });
        }
        html+='<section class="bd-pn'+st+'"><header><b>'+esc(head.toUpperCase())+'</b>'+(st===' nx'?'<i>NEXT</i>':(st===' past'?'<i class="d">DONE</i>':''))+'</header>'+body+'</section>';
    });
    var nx=md.next?dmap[md.next]:null, np=nx?parseDateAny(nx.date):null;
    var nextTxt = nx ? (np ? (nx.day.slice(0,3)+' '+np.d+' '+TL_MON[np.m-1]) : gzDate(nx)) : '';
    var marks=['Read a row across: all '+(isSaturdayLayout()?'streams':'classes')+' have lessons at the same time'];
    if(/<em>×2/.test(html)) marks.push('×2 double'); if(/bd-c/.test(html)) marks.push('↓ continues');
    el('pBody').innerHTML='<div class="tl bd'+(tight?' tight':'')+'">'
        + '<div class="bd-top">'+(offAll.length?'<span class="bd-cx">✕ No class: '+esc(offAll.join(', '))+'</span>':'<span></span>')
        + (nextTxt?'<span class="bd-next">Next · <b>'+esc(nextTxt.toUpperCase())+'</b></span>':'')+'</div>'
        + '<div class="tl-list bd-grid g'+Math.min(gsAll.length,4)+'">'+html+'</div>'
        + '<div class="bd-ft"><span>'+esc(marks.join(' · '))+'</span><span>Printed '+tlPrinted()+'</span></div></div>';
}

// ---------- "Quiet" theme ----------
// A calm, typographic sheet: white paper, one accent colour, hairline rules.
// One header row per column (Date · Time · SS1 · SS2 · SS3), then one block
// per date with a row per period, so reading a row across shows what every
// class/stream has at that moment. Lessons shared by all classes for 2+
// periods become one panel; the coming date is tinted and tagged NEXT.
// Exports split the dates into 2 (portrait) or 3 (landscape, 3+ classes)
// columns; the export re-renders once the page orientation is known.
function isQuiet(){ return el('theme').value==='quiet'; }
function qtCols(nGroups){
    if(_forceCols) return _forceCols;   // export picks the count that reads best
    var sh=el('sheet');
    if(!sh.classList.contains('exporting')) return 2;
    if(sh.classList.contains('portrait')) return 2;
    return nGroups>=3 ? 3 : 2;
}
function renderQuietSheet(){
    var md=tlModel(), periods=md.periods, dmap=md.dmap, order=md.order;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var real=order.filter(function(k){ return !dmap[k].off; });
    var nextIdx=md.next?real.indexOf(md.next):-1;
    var gsAll = md.anyGroup ? md.groupsAll : [''];
    var tight = gsAll.length>2;
    var who = isSaturdayLayout()?'streams':'classes';
    // Long full names are shortened when three or more classes share a row.
    var label=function(t){
        var raw=(t||'').trim();
        if(!tight) return esc(raw).replace(/\s*\/\s*/g,'<i>/</i><wbr>');
        var caps = raw===raw.toUpperCase();
        return raw.split('/').map(function(p){ p=p.trim(); var sh=BD_SHORT[p.toUpperCase()];
            if(sh && !caps) sh=sh.charAt(0)+sh.slice(1).toLowerCase();
            return esc(sh||p); }).join('<i>/</i><wbr>');
    };
    var tmpl='grid-template-columns:2.25em 2.1em repeat('+gsAll.length+',minmax(0,1fr))';
    var gap=function(i){ return i>0 && periods[i-1].end && periods[i-1].end<periods[i].start; };
    var blocks=[];
    order.forEach(function(k){
        var d=dmap[k], p=parseDateAny(d.date);
        var num = p ? ('0'+p.d).slice(-2) : esc((d.day||'').slice(0,3));
        var sub = p ? (esc((d.day||dayFromDate(d.date)||'').slice(0,3))+' · '+TL_MON[p.m-1].charAt(0)+TL_MON[p.m-1].slice(1).toLowerCase()) : esc(d.label||'');
        if(d.off){
            blocks.push({w:.3, h:'<div class="qt-bl off" style="'+tmpl+'"><div class="qt-dt"><b>'+num+'</b><span>'+sub+'</span></div><div class="qt-nc">No class</div></div>'});
            return;
        }
        var i0=real.indexOf(k), st = k===md.next ? ' nx' : (nextIdx>=0 && i0<nextIdx ? ' past' : '');
        var gs = md.anyGroup ? gsAll : [''];
        var g='', rowsT=[], r=0;
        var rowOf={};
        periods.forEach(function(pd,i){ if(gap(i)){ r++; rowsT.push('auto'); } r++; rowOf[i]=r; rowsT.push('minmax(0,1fr)'); });
        var nr=rowsT.length || 1;
        g+='<div class="qt-dt" style="grid-row:1 / span '+nr+'"><b>'+num+'</b><span>'+sub+'</span>'+(st===' nx'?'<em>Next</em>':'')+'</div>';
        var hasCells=(d.groups||[]).length && periods.some(function(pd){ return gs.some(function(gr){ return (d.cells[gr+'§'+pd.k]||[]).length; }); });
        if(!hasCells && d.banners.length){
            g+='<div class="qt-sk" style="grid-row:1 / span '+nr+';grid-column:2 / -1">'+d.banners.map(function(b){ return '<b>'+esc(b.subject||'')+'</b>'
                + ((b.teacher||'').trim()?'<span>'+esc(b.teacher)+'</span>':''); }).join('')+'</div>';
        } else {
            var runs=tlRuns(d,gs,periods);
            periods.forEach(function(pd,i){
                if(gap(i)) g+='<span class="qt-bk" style="grid-row:'+(rowOf[i]-1)+'">Break · '+esc(fmtT(periods[i-1].end))+' – '+esc(fmtT(pd.start))+'</span>';
                g+='<span class="qt-tm" style="grid-row:'+rowOf[i]+'">'+esc(fmtT(pd.start))+'</span>';
            });
            for(var i=0;i<periods.length;){
                if(runs[i]){
                    var ri=tlRunInfo(d,gs,periods,i,runs[i]);
                    g+='<div class="qt-sk" style="grid-row:'+rowOf[i]+' / '+(rowOf[runs[i]-1]+1)+';grid-column:3 / -1"><b>'+esc(ri.r.subject||'')+'</b>'
                        + '<span>'+esc([ri.who?ri.who+' together':'', (ri.r.teacher||'').trim()].filter(Boolean).join(' · '))+(ri.who||(ri.r.teacher||'').trim()?' · ':'')+'<u>'+esc(ri.from+(ri.to?' – '+ri.to:''))+'</u></span></div>';
                    i=runs[i]; continue;
                }
                gs.forEach(function(gr,li){
                    var arr=d.cells[gr+'§'+periods[i].k]||[], sg=sig(arr);
                    if(sg && i>0 && !gap(i) && sg===sig(d.cells[gr+'§'+periods[i-1].k]||[])) return;
                    var j=i+1; while(sg && j<periods.length && !gap(j) && !runs[j] && sig(d.cells[gr+'§'+periods[j].k]||[])===sg) j++;
                    var n=j-i;
                    var inner = arr.length ? arr.map(function(x){ return '<b>'+label(x.subject)+'</b>'; }).join('')
                        + (arr.length===1 && (arr[0].teacher||'').trim() ? '<small>'+esc(arr[0].teacher)+'</small>' : '')
                        + (n>1 ? '<em>'+(n===2?'Double period':n+' periods')+'</em>' : '') : '<b class="f">—</b>';
                    g+='<div class="qt-sb" style="grid-row:'+rowOf[i]+' / '+(rowOf[i+n-1]+1)+';grid-column:'+(li+3)+'">'+inner+'</div>';
                });
                i++;
            }
            d.banners.forEach(function(b){ g+='<div class="qt-sk" style="grid-column:2 / -1"><b>'+esc(b.subject||'')+'</b></div>'; });
        }
        blocks.push({w:1, h:'<div class="qt-bl'+st+'" style="'+tmpl+';grid-template-rows:'+rowsT.join(' ')+'">'+g+'</div>'});
    });
    // split into balanced columns
    var nc=Math.min(qtCols(gsAll.length), Math.max(1, blocks.length));
    var tot=blocks.reduce(function(a,b){ return a+b.w; },0), cols=[], acc=0;
    for(var c=0;c<nc;c++) cols.push('');
    blocks.forEach(function(b){ var ci=Math.min(nc-1, Math.floor((acc+b.w/2)/tot*nc)); cols[ci]+=b.h; acc+=b.w; });
    var hdr='<div class="qt-ch" style="'+tmpl+'"><span>Date</span><span>Time</span>'+gsAll.map(function(gr){ return '<span>'+esc(gr||'Lesson')+'</span>'; }).join('')+'</div>';
    var nx=md.next?dmap[md.next]:null, np=nx?parseDateAny(nx.date):null;
    var nextTxt = nx ? (np ? (nx.day.slice(0,3)+' '+np.d+' '+TL_MON[np.m-1].charAt(0)+TL_MON[np.m-1].slice(1).toLowerCase()) : gzDate(nx)) : '';
    el('pBody').innerHTML='<div class="tl qt">'
        + (nextTxt?'<div class="qt-next"><span>Next class</span><b>'+esc(nextTxt)+'</b></div>':'')
        + '<div class="qt-cols" style="--nc:'+nc+'">'+cols.map(function(c){ return '<div class="qt-col">'+hdr+'<div class="tl-list qt-bls">'+c+'</div></div>'; }).join('')+'</div>'
        + '<div class="qt-ft"><span>Read each row across — all '+who+' have lessons at the same time</span><span>Printed '+tlPrinted()+'</span></div></div>';
}

// ---------- "Inline" theme ----------
// Reads like a well-formatted message: one white card per date, and each
// period is ONE line — "9:00  [SS1] Bio  [SS2] English  [SS3] Maths" — so
// everything on a line is visibly happening at the same time. Classes are
// told apart by small coloured tags; a lesson every class shares for 2+
// periods (Skill Acquisition) is a single highlighted line.
var IL_TAGS=[['#4338ca','#e0e7ff'],['#047857','#d1fae5'],['#c2410c','#ffedd5'],['#be185d','#fce7f3'],['#0e7490','#cffafe'],['#a16207','#fef3c7']];
var IL_MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
function isInline(){ return el('theme').value==='inline'; }
function ilTag(g){ var w=(g||'').trim().split(/\s+/)[0]||''; return w.length>5 ? w.slice(0,3) : w; }
function renderInlineSheet(){
    var md=tlModel(), periods=md.periods, dmap=md.dmap, order=md.order;
    if(!periods.length && !order.some(function(k){ return dmap[k].banners.length; })){
        el('pBody').innerHTML='<p style="text-align:center;color:#888;padding:1.5rem">Add sessions with a day, time and subject to build the timetable.</p>';
        return;
    }
    var sig=function(arr){ return arr.map(function(r){ return r.subject+'|'+r.teacher; }).join('§'); };
    var real=order.filter(function(k){ return !dmap[k].off; });
    var nextIdx=md.next?real.indexOf(md.next):-1;
    var gsAll = md.anyGroup ? md.groupsAll : [''];
    var tight = gsAll.length>2;
    var who = isSaturdayLayout()?'streams':'classes';
    var label=function(t){
        var raw=(t||'').trim(); if(!tight) return esc(raw).replace(/\s*\/\s*/g,'/<wbr>');
        var caps = raw===raw.toUpperCase();
        return raw.split('/').map(function(p){ p=p.trim(); var sh=BD_SHORT[p.toUpperCase()];
            if(sh && !caps) sh=sh.charAt(0)+sh.slice(1).toLowerCase(); return esc(sh||p); }).join('/<wbr>');
    };
    var pill=function(li, inner){ var c=IL_TAGS[li%IL_TAGS.length];
        return '<u style="--c:'+c[0]+';--b:'+c[1]+'">'+(gsAll[li]?'<i>'+esc(ilTag(gsAll[li]))+'</i>':'')+inner+'</u>'; };
    var gap=function(i){ return i>0 && periods[i-1].end && periods[i-1].end<periods[i].start; };
    var heading=function(d){ var p=parseDateAny(d.date), day=d.day||dayFromDate(d.date)||'';
        return p ? (esc(day)+' '+p.d+' '+IL_MONTHS[p.m-1]) : esc(d.label||day); };
    var cards=[];
    order.forEach(function(k){
        var d=dmap[k];
        if(d.off){ cards.push({w:.35, h:'<div class="il-dy off"><h3><b>'+heading(d)+'</b></h3><p class="il-nc">No class</p></div>'}); return; }
        var i0=real.indexOf(k), st = k===md.next ? ' nx' : (nextIdx>=0 && i0<nextIdx ? ' past' : '');
        var gs = md.anyGroup ? gsAll : [''];
        var lines='';
        var hasCells=(d.groups||[]).length && periods.some(function(pd){ return gs.some(function(g){ return (d.cells[g+'§'+pd.k]||[]).length; }); });
        if(hasCells){
            var runs=tlRuns(d,gs,periods);
            for(var i=0;i<periods.length;){
                if(gap(i)) lines+='<p class="il-bk">Break · '+esc(fmtT(periods[i-1].end))+' – '+esc(fmtT(periods[i].start))+'</p>';
                if(runs[i]){
                    var ri=tlRunInfo(d,gs,periods,i,runs[i]);
                    lines+='<p class="il-ln sk"><time>'+esc(fmtT(periods[i].start))+'</time><span><b>'+esc(ri.r.subject||'')+'</b> <em>· '
                        + esc([ri.who?ri.who.replace(/^All /,'all '):'', ri.to?'until '+ri.to:'', (ri.r.teacher||'').trim()].filter(Boolean).join(', '))+'</em></span></p>';
                    i=runs[i]; continue;
                }
                var parts='';
                gs.forEach(function(g,li){
                    var arr=d.cells[g+'§'+periods[i].k]||[], sg=sig(arr);
                    if(sg && i>0 && !gap(i) && sg===sig(d.cells[g+'§'+periods[i-1].k]||[])){ parts+=pill(li,'<s>cont.</s>'); return; }
                    if(!arr.length){ parts+=pill(li,'<s>—</s>'); return; }
                    var dbl = i+1<periods.length && !gap(i+1) && sg===sig(d.cells[g+'§'+periods[i+1].k]||[]);
                    parts+=pill(li, arr.map(function(r){ return label(r.subject); }).join(' &amp; ')+(dbl?'<em>×2</em>':''));
                });
                lines+='<p class="il-ln"><time>'+esc(fmtT(periods[i].start))+'</time><span>'+parts+'</span></p>';
                i++;
            }
        }
        d.banners.forEach(function(b){ lines+='<p class="il-ln sk"><time>'+(b.time?esc(fmtT(b.time)):'')+'</time><span><b>'+esc(b.subject||'')+'</b>'
            + ((b.teacher||'').trim()?' <em>· '+esc(b.teacher)+'</em>':'')+'</span></p>'; });
        cards.push({w:1, h:'<div class="il-dy'+st+'"><h3><b>'+heading(d)+'</b>'+(st===' nx'?'<em>Next class</em>':(st===' past'?'<small>done</small>':''))+'</h3>'+lines+'</div>'});
    });
    var nc=Math.min(qtCols(3), Math.max(1, cards.length));
    var tot=cards.reduce(function(a,b){ return a+b.w; },0), cols=[], acc=0;
    for(var c=0;c<nc;c++) cols.push('');
    cards.forEach(function(b){ var ci=Math.min(nc-1, Math.floor((acc+b.w/2)/tot*nc)); cols[ci]+=b.h; acc+=b.w; });
    var nx=md.next?dmap[md.next]:null, np=nx?parseDateAny(nx.date):null;
    var nextTxt = nx ? (np ? ((nx.day||dayFromDate(nx.date)).slice(0,3)+' '+np.d+' '+IL_MONTHS[np.m-1].slice(0,3)) : gzDate(nx)) : '';
    var leg = md.anyGroup ? gsAll.map(function(g,li){ return pill(li, esc(g)); }).join('') : '';
    el('pBody').innerHTML='<div class="tl il'+(tight?' tight':'')+'">'
        + ((leg||nextTxt)?'<div class="il-top"><div class="il-lg">'+leg+'</div>'+(nextTxt?'<span class="il-next">Next class<b>'+esc(nextTxt)+'</b></span>':'')+'</div>':'')
        + '<div class="il-cols" style="--nc:'+nc+'">'+cols.map(function(c){ return '<div class="tl-list il-col">'+c+'</div>'; }).join('')+'</div>'
        + '<div class="il-ft"><span>Each line is one time — every '+(who==='streams'?'stream':'class')+' on that line is in a lesson at the same time'+(/<em>×2/.test(cols.join(''))?' · ×2 double':'')+'</span><span>Printed '+tlPrinted()+'</span></div></div>';
}

function renderSheet(){
    el('sheet').setAttribute('data-theme', el('theme').value);
    renderHead();
    applySaturdayDates();
    // A multi-page export renders one page's dates at a time.
    var allRows = null;
    if(_pageKeys){ allRows = rows; rows = rows.filter(function(r){ return _pageKeys[rowKey(r)]; }); }
    try{
        if(isBlankGrid()) renderBlankGridSheet();
        else if(tlUsesTimeline()) (isTickets() ? renderTicketsSheet() : isGazette() ? renderGazetteSheet() : isSwiss() ? renderSwissSheet() : isNotebook() ? renderNotebookSheet() : isBoard() ? renderBoardSheet() : isQuiet() ? renderQuietSheet() : isInline() ? renderInlineSheet() : renderTimelineSheet());
        else if(layout().mode==='grid') (el('orient').value==='cols' ? renderGridColumnsSheet() : renderGridModeSheet());
        else renderListSheet();
    } finally { if(allRows) rows = allRows; }
}
// The key a session is grouped under (same rule as tlModel: date, else day).
function rowKey(r){ var date=r.date||''; return date || (r.day||'').trim() || '—'; }

// Show/hide the editor panels for the current layout. Pure UI — never resets
// entered data, so it is safe to call when loading a saved design.
function syncLayoutUI(){
    var blank = isBlankGrid();
    var isGridMode = !blank && layout().mode==='grid';
    el('gridEditor').style.display = blank?'block':'none';
    el('rowEditor').style.display = blank?'none':'block';
    // For rosters, swap the free-text "Column headers" box for a "students per row"
    // count (the columns are numbered name-boxes, one student each).
    var listTable = isListTable();
    el('gridColsWrap').style.display = isRoster() ? 'none' : '';
    el('rosterCountWrap').style.display = isRoster() ? '' : 'none';
    // the auto-numbered table uses a row-count + its own paste box; it has no
    // manual row-label list.
    el('listRowsWrap').style.display = listTable ? '' : 'none';
    el('gridRowsWrap').style.display = listTable ? 'none' : '';
    el('listPasteBox').style.display = listTable ? 'block' : 'none';
    // grid paste & the orientation choice only apply to the day×period layouts
    el('gridPasteBox').style.display = isGridMode ? 'block':'none';
    el('orientWrap').style.display = isGridMode ? 'block':'none';
    // the Saturday first-date + lesson-free planner only applies to Saturday classes
    el('satPanel').style.display = isSaturdayLayout() ? 'block':'none';
    el('gridRowsLabel').textContent = isRoster()
        ? 'Row labels — one per line (e.g. Week 1, Week 2 … or Monday, Tuesday …)'
        : 'Row labels — one per line (e.g. period times)';
    // The fill tip applies to every editable grid (rosters + the blank grid).
    var tip = el('rosterTip');
    if(isBlankGrid()){
        tip.style.display = 'block';
        tip.innerHTML = isRoster()
            ? '<i class="fas fa-hand-pointer"></i> Click any box and type <b>one student\'s name per box</b>. Set how many per week/day with “Students per week / day” above. What you type prints and exports.'
            : listTable
            ? '<i class="fas fa-hand-pointer"></i> Type into each auto-numbered row. Edit the <b>column headers</b> and set the <b>number of rows</b> above — or paste the whole table at once (button below). What you type prints and exports.'
            : '<i class="fas fa-hand-pointer"></i> Click any box and type to build <b>any</b> timetable. Edit the <b>column headers</b> and <b>row labels</b> above to add/rename columns and rows. What you type prints and exports; leave a box blank to fill it by hand.';
    } else {
        tip.style.display = 'none';
    }
}
function onLayoutChange(){
    var v=el('layout').value;
    var blank = isBlankGrid();
    // A roster drops in its matching template (weeks×days or days×duty) and starts a
    // fresh set of cells, since switching axis changes what each cell means.
    if(ROSTER_PRESETS[v]){
        el('gridRows').value=ROSTER_PRESETS[v].rows;
        el('gridCols').value=rosterCols();
        rosterCells={};
    }
    // Entering the custom table drops in sensible starter headers ONLY when the
    // headers still look like the day-grid default — so re-entering a table you
    // customised never wipes your headers or typed cells.
    if(v==='list_table' && /\bMonday\b/.test(el('gridCols').value)){
        el('gridCols').value='Name, Subject, Branch, Number';
    }
    syncLayoutUI();
    if(!el('title').dataset.touched){ el('title').value=''; }
    if(!blank) renderEditor();
    renderManageSaturdays();
    renderSheet();
}
// Save typed roster-cell text so it survives re-renders and the PDF/image export.
el('pBody').addEventListener('input', function(e){
    var td = e.target.closest && e.target.closest('[data-rc]');
    if(td){ rosterCells[td.getAttribute('data-rc')] = td.textContent; }
});
el('layout').addEventListener('change', onLayoutChange);
el('rosterCount').addEventListener('input', function(){
    if(isRoster()){ el('gridCols').value=rosterCols(); renderSheet(); }
});
el('theme').addEventListener('change', renderSheet);
el('orient').addEventListener('change', renderSheet);
// Logo toggle: hides/shows the <img> in the live preview — since export
// captures this same DOM (html2canvas), the PDF/image download honours it
// too, with no separate export-side logic needed.
if(el('showLogo')){
    el('showLogo').addEventListener('change', function(){
        var img = el('pLogo');
        if(img) img.style.display = this.checked ? '' : 'none';
    });
}
el('title').addEventListener('input', function(){ this.dataset.touched='1'; });
// Saturday planner: set the first Saturday, then tick lesson-free Saturdays.
el('satFirst').addEventListener('change', function(){
    saturdayPlan.first = this.value; renderManageSaturdays(); renderSheet();
});
el('satManage').addEventListener('change', function(e){
    var cb = e.target.closest && e.target.closest('input[type="checkbox"][data-iso]');
    if(!cb) return;
    var iso = cb.getAttribute('data-iso');
    if(cb.checked) saturdayPlan.free[iso]=true; else delete saturdayPlan.free[iso];
    renderManageSaturdays(); renderSheet();
});

// ---------- export (Full-HD image / PDF) with preview ----------
// The exported PNG/PDF is a html2canvas screenshot of the SAME #sheet DOM the
// live designer renders — there is no separate export layout to keep in
// sync. Sizing it correctly (this file's real fix) therefore only has to
// happen once, in the table's own <colgroup>-driven CSS: whatever width the
// sheet is captured at (landscape or portrait), every column is already an
// exact percentage of it, so html2canvas/jsPDF have nothing left to
// recalculate — they just rasterise the layout that's already correct.
var _exportOrientation = 'landscape';
var _exportPaper = 'a4';   // 'a4' or 'a3' (PDF pages)
function exportName(){
    return (el('title').value || layout().title || 'timetable').replace(/[^\w]+/g, '_');
}
// ---------- Export: readable text, as many A4 pages as it takes ----------
// These sheets are mostly shared as images/PDFs and read on a phone, where an
// A4 page is shown at ~37% (portrait) or ~26% (landscape) of its size. So the
// user picks Small/Medium/Large, which fixes the size of the main text, and
// it is NEVER shrunk to squeeze everything onto one page: dates that don't
// fit flow onto the next page instead (PDF pages / one image per page).
// Sizes are sheet px for the main subject text (portrait sheet 1046px wide,
// landscape 1480px); on a phone Medium is ~11.5px portrait / ~10px landscape.
var EXPORT_TEXT = {portrait:{s:24, m:28, l:33}, landscape:{s:27, m:31, l:37}};
var EXPORT_MIN_RATIO = 0.72;   // no text (teachers, labels, footers) below this share of it
var _pageKeys = null;           // dates on the page being rendered (null = all)
var _pageLabel = '';
var _laterPage = false;          // rendering page 2+ of a multi-page export
var _allFirst = null, _allLast = null;   // first/last date of a multi-page export            // 'Page 2 of 3' in the subtitle while exporting several pages
var _exportPages = [];          // [{url, w, h}] of the last finished render
var _floored = [];
function exportSize(){ var r=document.querySelector('input[name="exportSize"]:checked'); return r ? r.value : 'm'; }
function exportTextPx(){ return EXPORT_TEXT[_exportOrientation==='portrait'?'portrait':'landscape'][exportSize()] || 31; }
function pageHeight(sheet){ var w=sheet.offsetWidth; return _exportOrientation==='portrait' ? w*297/210 : w*210/297; }
function scaleRoot(){ return document.querySelector('#pBody .tl') || document.querySelector('#pBody table') || el('pBody'); }
// The size the timetable's main text (the subject names) is set in.
function mainTextPxAll(root){   // whole sheet, for a page with no date list text
    var tally={}, n, w=document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while((n=w.nextNode())){ var t=n.nodeValue.trim(); if(!t || !n.parentElement) continue;
        var fs=Math.round(parseFloat(getComputedStyle(n.parentElement).fontSize)*2)/2; tally[fs]=(tally[fs]||0)+t.length; }
    var total=0, best=0; for(var k in tally) total+=tally[k];
    Object.keys(tally).map(Number).sort(function(a,b){ return b-a; }).some(function(sz){ if(tally[sz]>=total*0.25){ best=sz; return true; } return false; });
    return best;
}
function mainTextPx(root){
    // Measure the timetable itself, not keys, legends or footers.
    var lists=root.querySelectorAll('.tl-list, .gz-lead'), scopes=lists.length ? Array.prototype.slice.call(lists) : [root];
    var tally={}, best=0, bestN=0, n;
    scopes.forEach(function(sc){ var w=document.createTreeWalker(sc, NodeFilter.SHOW_TEXT);
    while((n=w.nextNode())){
        var t=n.nodeValue.trim(); if(!t || !n.parentElement) continue;
        var fs=Math.round(parseFloat(getComputedStyle(n.parentElement).fontSize)*2)/2;
        tally[fs]=(tally[fs]||0)+t.length;
    } });
    // The biggest size that carries a good share (25%+) of the text: the
    // subject names, even where smaller teacher names add up to more letters.
    var total=0; for(var k in tally) total+=tally[k];
    Object.keys(tally).map(Number).sort(function(a,b){ return b-a; }).some(function(sz){
        if(tally[sz] >= total*0.25){ best=sz; return true; } return false; });
    if(!best) for(var k2 in tally) if(tally[k2]>bestN){ bestN=tally[k2]; best=+k2; }
    if(!best) best = mainTextPxAll(root);
    return best;
}
function setMainText(px){
    var root=scaleRoot(); root.style.fontSize='22px';
    for(var i=0;i<4;i++){
        var cur=parseFloat(root.style.fontSize), m=mainTextPx(root); if(!m) break;
        var nx=cur*px/m; if(Math.abs(nx-cur)<0.25) break;
        root.style.fontSize=nx+'px';
    }
}
// Lift any small print (teacher names, labels, footers, header lines) to a
// readable minimum. Parents come before children in document order, so a
// lifted parent's em-sized children are re-measured after it grows.
function floorText(scope, min){
    Array.prototype.forEach.call(scope.querySelectorAll('*'), function(e){
        if(!Array.prototype.some.call(e.childNodes, function(c){ return c.nodeType===3 && c.nodeValue.trim(); })) return;
        if(parseFloat(getComputedStyle(e).fontSize) < min-0.3){ e.style.fontSize=min+'px'; _floored.push(e); }
    });
}
function clearFloor(){ _floored.forEach(function(e){ e.style.fontSize=''; }); _floored=[]; }
// Column layouts to try for the current theme on an export page. Fewer
// columns = wider cells (no word ever breaks mid-word at the bigger sizes);
// more = more dates per page. Each page uses whichever fits the most.
var _forceCols = 0;   // Quiet/Inline split their dates into columns in JS
function columnChoices(){
    if(!tlUsesTimeline()) return [null];
    var land = _exportOrientation !== 'portrait';
    var grid = function(sel, ns){ return ns.map(function(n){ return {n:n, post:function(){
        var g=document.querySelector('#pBody '+sel); if(g) g.style.gridTemplateColumns='repeat('+n+',minmax(0,1fr))'; }}; }); };
    if(isQuiet() || isInline()) return (land ? [1,2,3] : [1,2]).map(function(n){ return {n:n, pre:n}; });
    if(isTimeline()) return [1,2].map(function(n){ return {n:n, post:function(){
        var sp=document.querySelector('#pBody .tl-split'); if(!sp) return;
        sp.style.flexDirection = n>1 ? 'row' : 'column';
        Array.prototype.forEach.call(sp.querySelectorAll('.tl-half+.tl-half .tl-hd'), function(h){ h.style.display = n>1 ? 'grid' : 'none'; });
    }}; });
    if(isBoard()) return grid('.bd-grid', land ? [1,2,3,4] : [1,2,3]);
    if(isTickets()) return grid('.tk-grid', land ? [1,2,3,4] : [1,2,3]);
    if(isSwiss()) return grid('.sw-grid', land ? [1,2,3,4] : [1,2,3]);
    if(isNotebook()) return grid('.nb-grid', land ? [1,2,3,4] : [1,2,3]);
    // Gazette: the lead date sits above the date columns (side by side, the
    // lead column leaves too little room at readable sizes).
    if(isGazette()) return [1,2,3].map(function(n){ return {n:n, post:function(){
        var c=document.querySelector('#pBody .gz-cols'); if(c) c.style.gridTemplateColumns='repeat('+n+',minmax(0,1fr))';
        var b=document.querySelector('#pBody .gz-body'); if(b){ b.style.gridTemplateColumns='minmax(0,1fr)'; b.classList.add('gz-stack'); }
    }}; });
    return [null];
}
// Text that doesn't read: a word broken across lines, or cut off by its box.
function badTextNodes(scope){
    var bad=[], rects=[], n, w=document.createTreeWalker(scope, NodeFilter.SHOW_TEXT), rg=document.createRange();
    while((n=w.nextNode())){
        var t=n.nodeValue.trim(); if(!t || !/[A-Za-z0-9]/.test(t)) continue;
        if(n.parentElement && n.parentElement.closest('[aria-hidden="true"]')) continue;   // decoration
        var words=t.split(/[\s\/]+/).filter(Boolean).length;
        rg.selectNodeContents(n);
        var tops={}, lines=0;
        Array.prototype.forEach.call(rg.getClientRects(), function(r){ if(r.width>0){ var k=Math.round(r.top/3); if(!tops[k]){ tops[k]=1; lines++; } } });
        var p=n.parentElement, cs=p && getComputedStyle(p);
        // ...or spilling out of its cell/column over the next one
        var box=p; while(box && box!==scope && getComputedStyle(box).display.indexOf('inline')===0) box=box.parentElement;
        var tr=rg.getBoundingClientRect(), br=box && box.getBoundingClientRect();
        var spill = br && br.width>0 && (tr.right>br.right+3 || tr.left<br.left-3);
        if(lines>words || spill || (cs && cs.overflow!=='visible' && p.scrollWidth>p.clientWidth+2)) bad.push(n);
        else Array.prototype.forEach.call(rg.getClientRects(), function(r){ if(r.width>1 && r.height>1) rects.push({n:n, r:r}); });
    }
    // ...or printed over another piece of text (a box wider than its column)
    rects.sort(function(a,b){ return a.r.left-b.r.left; });
    for(var i=0;i<rects.length;i++){
        var A=rects[i].r;
        for(var j=i+1;j<rects.length && rects[j].r.left < A.right-3;j++){
            var B=rects[j].r;
            if(rects[j].n===rects[i].n) continue;
            if(Math.min(A.bottom,B.bottom)-Math.max(A.top,B.top) > Math.min(A.height,B.height)*0.35){
                if(bad.indexOf(rects[i].n)<0) bad.push(rects[i].n);
                if(bad.indexOf(rects[j].n)<0) bad.push(rects[j].n);
            }
        }
    }
    return bad;
}
// The short forms schools write on timetables, used only where the full
// name would break or be cut off at the chosen text size.
var SHORT_NAMES = {'mathematics':'Maths','further mathematics':'F. Maths','civic education':'Civic','government':'Govt',
  'chemistry':'Chem','biology':'Bio','physics':'Phy','literature':'Lit','literature in english':'Lit','economics':'Econs',
  'commerce':'Comm','data processing':'Data Proc.','agric science':'Agric','agricultural science':'Agric',
  'geography':'Geo','english language':'English','christian religious studies':'CRS','islamic religious studies':'IRS',
  'computer studies':'Computer','computer science':'Computer','technical drawing':'Tech. Drw.','financial accounting':'Accounts',
  'home economics':'Home Econs','business studies':'Bus. Studies','basic science':'Basic Sci.','basic technology':'Basic Tech.',
  'social studies':'Social St.','physical and health education':'PHE','cultural and creative arts':'CCA','skill acquisition':'Skills',
  'arts & comm.':'Arts','arts & commercial':'Arts','commercial':'Comm.'};
function shortenText(t){
    var lead=t.match(/^\s*/)[0], trail=t.match(/\s*$/)[0], core=t.trim();
    var out=core.split(/(\s*\/\s*)/).map(function(part){
        var sh=SHORT_NAMES[part.trim().toLowerCase()];
        if(!sh) return part;
        return part.trim()===part.trim().toUpperCase() ? sh.toUpperCase() : sh;
    }).join('');
    return out===core ? null : lead+out+trail;
}
function shortenBroken(scope){
    var changed=0;
    badTextNodes(scope).forEach(function(n){ var t=shortenText(n.nodeValue); if(t){ n.nodeValue=t; changed++; } });
    return changed;
}
// Render the dates in `keys` (null = all) for export at the chosen text size,
// in column layout `cand`; returns the sheet height and how much text breaks.
function layoutPage(keys, sheet, cand){
    _pageKeys = keys ? keys.reduce(function(o,k){ o[k]=1; return o; }, {}) : null;
    _forceCols = (cand && cand.pre) || 0;
    _laterPage = !!(keys && _allFirst && keys[0] !== _allFirst);
    // Title/header only on the first page, keys and footer only on the last.
    sheet.classList.toggle('pg-nohead', !!(keys && _allFirst && keys[0] !== _allFirst));
    sheet.classList.toggle('pg-nofoot', !!(keys && _allLast && keys[keys.length-1] !== _allLast));
    clearTableExportSizing(); clearFloor();
    renderSheet();
    var px=exportTextPx();
    sheet.style.fontSize = Math.round(px*0.82)+'px';   // header and title grow with the text
    setMainText(px);
    floorText(sheet, Math.round(px*EXPORT_MIN_RATIO));
    if(cand && cand.post) cand.post();
    if(shortenBroken(el('pBody'))) shortenBroken(el('pBody'));
    return {h: sheet.offsetHeight, bad: badTextNodes(el('pBody')).length};
}
// Column layouts for these dates, each with its height and broken-text count.
function tryLayouts(keys, sheet){
    return columnChoices().map(function(c){ var r=layoutPage(keys, sheet, c); r.cand=c; return r; });
}
// The layout to use for a page of these dates: of those that fit the page
// and read as well as this theme can (`tol` broken words per date), the one
// with the most columns' worth of room saved; else the shortest.
function pickLayout(rs, H, tol, n){
    var ok=rs.filter(function(r){ return r.h<=H && r.bad<=tol*n; });
    if(ok.length) return ok.reduce(function(a,b){ return b.bad<a.bad || (b.bad===a.bad && b.h<a.h) ? b : a; });
    return rs.reduce(function(a,b){ return b.bad<a.bad || (b.bad===a.bad && b.h<a.h) ? b : a; });
}
function canPaginate(){
    var v=el('layout').value;
    return !isBlankGrid() && !ROSTER_PRESETS[v] && v!=='list_table';
}
// Split the dates into pages: as many per page as fit readably at the chosen
// size, then evened out so the last page isn't a lonely leftover.
// Returns [{keys, cand}] (keys null = everything on one page).
function planPages(sheet){
    _pageKeys=null; _forceCols=0; _pageLabel=''; renderSheet();
    var all = canPaginate() ? tlModel().order.slice() : [];
    _allFirst = all[0] || null; _allLast = all[all.length-1] || null;
    var H = pageHeight(sheet) + 1;
    // How well this theme can do at all: the fewest broken words per date
    // over a few sample dates in any layout (some themes always break one).
    var tol = 0;
    if(all.length){
        var sample = all.slice(0, Math.min(3, all.length));
        tol = Math.min.apply(null, tryLayouts(sample, sheet).map(function(r){ return r.bad; })) / sample.length;
    }
    var whole = pickLayout(tryLayouts(null, sheet), H, tol, Math.max(1, all.length));
    if(all.length < 2 || (whole.h <= H && whole.bad <= tol*all.length)) return [{keys:null, cand:whole.cand}];
    _pageLabel = 'Page 9 of 9';   // same width as the real label
    var memo={};
    var fits=function(a,b){ var k=a+':'+b;
        if(!(k in memo)){ var r=pickLayout(tryLayouts(all.slice(a,b), sheet), H, tol, b-a); memo[k]={ok:r.h<=H && r.bad<=tol*(b-a)+1e-9, cand:r.cand}; }
        return memo[k]; };
    // Each page takes the most dates that fit. (Not "stop at the first that
    // doesn't": a different column layout may fit one more date.)
    var spans=[], i=0;
    while(i<all.length){
        var j=i+1, miss=0;
        for(var b=i+2; b<=all.length && miss<2; b++){ if(fits(i,b).ok){ j=b; miss=0; } else miss++; }
        spans.push([i,j]); i=j;
    }
    // Even the pages out (3+2 rather than 4+1) where that still fits.
    var P=spans.length, base=Math.floor(all.length/P), extra=all.length%P, even=[], s0=0;
    for(var q=0;q<P;q++){ var len=base+(q<extra?1:0); even.push([s0,s0+len]); s0+=len; }
    if(even.every(function(p){ return fits(p[0],p[1]).ok; })) spans=even;
    return spans.map(function(p){ return {keys:all.slice(p[0],p[1]), cand:fits(p[0],p[1]).cand}; });
}
function sizeTimelineForExport(sheet){
    var lists = document.querySelectorAll('#pBody .tl-list');
    if(!lists.length) return false;
    var list = lists[0];
    var canvasH = pageHeight(sheet);
    var extra = canvasH - sheet.offsetHeight;
    // A single date taller than a page (only then): shrink it to fit.
    var tl = document.querySelector('#pBody .tl');
    if(extra < 0 && tl){
        var fs = parseFloat(getComputedStyle(tl).fontSize) || 16;
        for(var k=0; k<12 && sheet.offsetHeight > canvasH; k++){
            fs *= Math.max(0.8, Math.min(0.985, Math.sqrt(canvasH / sheet.offsetHeight)));
            tl.style.fontSize = fs + 'px';
        }
        extra = canvasH - sheet.offsetHeight;
    }
    if(extra > 0){
        // Side-by-side lists each get all of the spare height; stacked ones share it.
        var stacked = lists.length > 1 && lists[1].getBoundingClientRect().top > list.getBoundingClientRect().bottom - 1;
        var each = stacked ? extra / lists.length : extra;
        var hs = Array.prototype.map.call(lists, function(l){ return l.offsetHeight; });
        if(!stacked){ var mx = Math.max.apply(null, hs); hs = hs.map(function(){ return mx; }); }
        Array.prototype.forEach.call(lists, function(l, i){ l.style.minHeight = (hs[i] + each) + 'px'; });
    }
    return true;
}
function sizeTableForExport(sheet){
    if(sizeTimelineForExport(sheet)) return;
    var table = document.querySelector('#pBody table');
    if(!table || !table.rows.length) return;
    var canvasH = pageHeight(sheet);
    // Too tall even alone (e.g. a roster): shrink the table to fit the page.
    for(var k=0; k<12 && sheet.offsetHeight > canvasH; k++){
        var fs = parseFloat(getComputedStyle(table).fontSize) || 16;
        table.style.fontSize = fs*Math.max(0.8, Math.min(0.985, Math.sqrt(canvasH/sheet.offsetHeight))) + 'px';
    }
    var cs = getComputedStyle(sheet);
    var padTop = parseFloat(cs.paddingTop) || 0, padBottom = parseFloat(cs.paddingBottom) || 0;
    var sheetContentTop = sheet.getBoundingClientRect().top + padTop;
    var usedBefore = table.getBoundingClientRect().top - sheetContentTop;
    var after = (sheet.getBoundingClientRect().bottom - padBottom) - table.getBoundingClientRect().bottom;
    var available = canvasH - padTop - padBottom - usedBefore - Math.max(0, after);
    var perRow = available / table.rows.length;
    if(perRow > 0) for(var i = 0; i < table.rows.length; i++) if(table.rows[i].offsetHeight < perRow) table.rows[i].style.height = perRow + 'px';
}
function clearTableExportSizing(){
    Array.prototype.forEach.call(document.querySelectorAll('#pBody .tl-list'), function(l){ l.style.minHeight = ''; });
    var bg = document.querySelector('#pBody .bd-grid'); if(bg) bg.style.gridTemplateColumns = '';
    var root = scaleRoot(); if(root) root.style.fontSize = '';
    var table = document.querySelector('#pBody table');
    if(!table) return;
    table.style.fontSize = '';
    for(var i = 0; i < table.rows.length; i++) table.rows[i].style.height = '';
}
// Only one render at a time. On a phone each page takes seconds; a size or
// orientation change mid-render used to start parallel renders that finished
// in reverse order (a stale one overwrote the preview) and ran phones out of
// graphics memory (green/blank blocks). A change mid-render now marks it
// stale: it stops after the current page and ONE fresh render starts.
var _capBusy = false, _capAgain = false;
function freeCanvas(c){ if(c){ c.width = 0; c.height = 0; } }
function captureExport(){
    el('exportImg').style.display = 'none';
    el('exportSpinner').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rendering…';
    el('exportSpinner').style.display = 'block';
    if(_capBusy){ _capAgain = true; return; }
    _capBusy = true;
    var sheet = el('sheet');
    _exportOrientation = (el('pageOrient') && el('pageOrient').value) || 'landscape';
    _exportPaper = (el('pagePaper') && el('pagePaper').value) || 'a4';
    var wrap = sheet.closest('.td-wrap');
    if(wrap) wrap.classList.add('td-exporting'); // phones hide the preview; keep it measurable
    sheet.classList.add('exporting');            // fills the A4 content width
    sheet.classList.toggle('portrait', _exportOrientation === 'portrait');
    // A3 is √2 wider than A4 at the same text size: same printed size, twice the room.
    sheet.classList.toggle('a3', _exportPaper === 'a3');
    var cleanup = function(){
        _pageKeys = null; _pageLabel = ''; _forceCols = 0; _laterPage = false; _allFirst = _allLast = null; sheet.classList.remove('pg-nohead','pg-nofoot'); clearFloor(); clearTableExportSizing();
        sheet.style.fontSize = '';
        sheet.classList.remove('exporting', 'portrait', 'a3');
        if(wrap) wrap.classList.remove('td-exporting');
        renderSheet();
        _capBusy = false;
    };
    var pages, out = [];
    try { pages = planPages(sheet); } catch(e){ pages = [{keys:null, cand:null}]; }
    var step = function(i){
        if(_capAgain || el('exportModal').style.display === 'none') return Promise.resolve('stale');
        if(i >= pages.length) return Promise.resolve('done');
        _pageLabel = pages.length > 1 ? 'Page '+(i+1)+' of '+pages.length : '';
        layoutPage(pages[i].keys, sheet, pages[i].cand);
        sizeTableForExport(sheet);
        var scale = Math.max(2, Math.ceil(1920 / (sheet.offsetWidth || 1480)));
        // Phone browsers can't draw canvases much over ~16 million pixels.
        scale = Math.max(1, Math.min(scale, Math.sqrt(15000000 / ((sheet.offsetWidth||1480) * (sheet.scrollHeight||1)))));
        return html2canvas(sheet, {scale: scale, backgroundColor: '#ffffff',
                    // Lay the copy out at desktop width so the designer's tablet/phone
                    // rules (which hide the preview) never apply to it.
                    windowWidth: Math.max(1400, sheet.scrollWidth), windowHeight: sheet.scrollHeight})
            .then(function(canvas){
                // Keep the pixels as a PNG and free the canvas straight away, so a
                // long timetable never holds several page-sized canvases at once.
                out.push({url: canvas.toDataURL('image/png'), w: canvas.width, h: canvas.height});
                freeCanvas(canvas);
                return step(i+1);
            });
    };
    step(0).then(function(res){
        cleanup();
        if(res === 'stale'){
            if(_capAgain){ _capAgain = false; captureExport(); }
            return;
        }
        _exportPages = out;
        showExportPages();
    }).catch(function(e){
        cleanup();
        if(_capAgain){ _capAgain = false; captureExport(); return; }
        el('exportSpinner').textContent = 'Could not render the timetable: ' + e;
    });
}
function showExportPages(){
    var box = el('exportImg'), n = _exportPages.length;
    box.innerHTML = _exportPages.map(function(p, i){
        return (n > 1 ? '<span class="export-pg">Page '+(i+1)+' of '+n+'</span>' : '') + '<img alt="Timetable page '+(i+1)+'" src="'+p.url+'">';
    }).join('');
    box.style.display = 'flex';
    el('exportSpinner').style.display = 'none';
    var b = document.querySelector('#exportModal [data-call="downloadPDF"]');
    if(b) b.innerHTML = '<i class="fas fa-file-pdf"></i> Download PDF <small>('+_exportPaper.toUpperCase()+(n > 1 ? ', '+n+' pages' : '')+')</small>';
}
function openExport(){
    var modal = el('exportModal');
    // Move the modal to <body> so its position:fixed is relative to the viewport
    // and not a transformed/scrolled ancestor — otherwise on mobile it opens
    // off-screen and you have to hunt for it. Also lock background scrolling.
    if(modal.parentNode !== document.body) document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';
    modal.style.display = 'flex';
    captureExport();
}
function closeExport(){ el('exportModal').style.display = 'none'; document.body.style.overflow = ''; }
// "Download image": ONE long image for phones/WhatsApp. Always phone-shaped
// (portrait width) at the chosen text size, as tall as the timetable needs —
// no pages, nothing shrunk. Rendered on demand (the preview shows the PDF).
function downloadImage(){
    if(_capBusy) return;
    var btn = document.querySelector('#exportModal [data-call="downloadImage"]');
    var label = btn ? btn.innerHTML : '';
    if(btn){ btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Making image…'; }
    _capBusy = true;
    var sheet = el('sheet'), wrap = sheet.closest('.td-wrap');
    var keepO = _exportOrientation;
    _exportOrientation = 'portrait';
    if(wrap) wrap.classList.add('td-exporting');
    sheet.classList.add('exporting', 'portrait');
    var done = function(){
        _pageKeys = null; _pageLabel = ''; _forceCols = 0; _laterPage = false; _allFirst = _allLast = null; sheet.classList.remove('pg-nohead','pg-nofoot');
        clearFloor(); clearTableExportSizing(); sheet.style.fontSize = '';
        sheet.classList.remove('exporting', 'portrait', 'a3');
        if(wrap) wrap.classList.remove('td-exporting');
        _exportOrientation = keepO;
        renderSheet();
        _capBusy = false;
        if(btn){ btn.disabled = false; btn.innerHTML = label; }
        if(_capAgain){ _capAgain = false; captureExport(); }
    };
    try {
        // The column layout that reads best (fewest broken words), then the most compact.
        _pageKeys = null; renderSheet();
        var rs = tryLayouts(null, sheet);
        var best = rs.reduce(function(a, b){ return b.bad < a.bad || (b.bad === a.bad && b.h < a.h) ? b : a; });
        layoutPage(null, sheet, best.cand);
    } catch(e){ layoutPage(null, sheet, null); }
    // Long sheets: drop the scale before a phone runs out of canvas memory.
    var w = sheet.offsetWidth || 1046, h = sheet.scrollHeight || 1;
    var scale = Math.max(1, Math.min(2, Math.sqrt(15000000 / (w * h))));
    html2canvas(sheet, {scale: scale, backgroundColor: '#ffffff', windowWidth: Math.max(1400, sheet.scrollWidth), windowHeight: h})
        .then(function(canvas){
            var url = canvas.toDataURL('image/png'); freeCanvas(canvas);
            done();
            var a = document.createElement('a'); a.href = url; a.download = exportName() + '.png'; a.click();
        })
        .catch(function(e){ done(); alert('Could not make the image: ' + e); });
}
function downloadPDF(){
    if(!_exportPages.length || _capBusy) return;   // never download a stale render
    var JsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
    var pdf = new JsPDF({orientation: _exportOrientation, unit: 'mm', format: _exportPaper});
    var pw = pdf.internal.pageSize.getWidth(), ph = pdf.internal.pageSize.getHeight();
    _exportPages.forEach(function(p, i){
        if(i) pdf.addPage(_exportPaper, _exportOrientation);
        // Fill the page width, keep the aspect ratio; fit to height if taller.
        var imgW = pw, imgH = pw * p.h / p.w;
        if(imgH > ph){ imgH = ph; imgW = ph * p.w / p.h; }
        pdf.addImage(p.url, 'PNG', (pw - imgW) / 2, 0, imgW, imgH);
    });
    pdf.save(exportName() + '.pdf');
}
// click outside the box closes the preview
document.getElementById('exportModal').addEventListener('click', function(e){
    if(e.target === this) closeExport();
});
// Orientation and text size re-render the preview (what the downloads use) —
// only while the modal is open. The chosen text size is remembered.
el('pageOrient').addEventListener('change', function(){
    if(el('exportModal').style.display !== 'none') captureExport();
});
if(el('pagePaper')) el('pagePaper').addEventListener('change', function(){
    try { localStorage.setItem('ttExportPaper', this.value); } catch(e){}
    if(el('exportModal').style.display !== 'none') captureExport();
});
try { var _pp = localStorage.getItem('ttExportPaper'); if(_pp && el('pagePaper') && el('pagePaper').querySelector('option[value="'+_pp+'"]')) el('pagePaper').value = _pp; } catch(e){}
(function(){
    var saved = null;
    try { saved = localStorage.getItem('ttExportSize'); } catch(e){}
    var r = saved && document.querySelector('input[name="exportSize"][value="'+saved+'"]');
    if(r) r.checked = true;
    Array.prototype.forEach.call(document.querySelectorAll('input[name="exportSize"]'), function(inp){
        inp.addEventListener('change', function(){
            try { localStorage.setItem('ttExportSize', inp.value); } catch(e){}
            if(el('exportModal').style.display !== 'none') captureExport();
        });
    });
})();

// seed with a couple of sessions so the tool is immediately usable
addRow(); addRow();
onLayoutChange();
// paint the "Saved timetables" badge/list from the server's first-paint data
try{ renderSavedList(INITIAL_SAVED||[]); }catch(e){}
