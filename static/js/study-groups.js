/* Study Groups board: render groups from the embedded JSON, let an admin
 * drag a student card into another group (or use the "Move to" dropdown --
 * same action, just without drag), pick a new leader, rename a group, and
 * export the board as a PNG via the already-vendored html2canvas. */
(function () {
  var dataEl = document.getElementById('sg-data');
  if (!dataEl) return;
  var DATA = JSON.parse(dataEl.textContent);
  var board = document.getElementById('sgBoard');
  var esc = window.escapeHtml || function (s) { return s; };

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }

  function post(url, params) {
    var body = new URLSearchParams(params);
    body.set('_csrf_token', csrf());
    return fetch(url, {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }, body: body,
    }).then(function (r) { return r.json(); });
  }

  function fmtAvg(v) {
    return v === null || v === undefined ? '' : ' (' + Math.round(v * 10) / 10 + ')';
  }

  function render() {
    board.innerHTML = '';
    DATA.groups.forEach(function (g) {
      var card = document.createElement('div');
      card.className = 'sg-group';
      card.setAttribute('data-group-id', g.id);

      var hdr = document.createElement('div');
      hdr.className = 'sg-group-hdr';
      var labelInput = document.createElement('input');
      labelInput.className = 'sg-label';
      labelInput.value = g.label;
      labelInput.setAttribute('aria-label', 'Group name');
      labelInput.addEventListener('change', function () {
        post(DATA.urls.rename, { group_id: g.id, label: labelInput.value }).then(function (res) {
          if (res.ok) labelInput.value = res.label;
        });
      });
      hdr.appendChild(labelInput);
      var count = document.createElement('span');
      count.className = 'muted';
      count.style.fontSize = '.75rem';
      count.textContent = g.members.length;
      hdr.appendChild(count);
      card.appendChild(hdr);

      g.members.forEach(function (m) {
        card.appendChild(renderMember(m, g));
      });

      card.addEventListener('dragover', function (e) {
        e.preventDefault();
        card.classList.add('drag-over');
      });
      card.addEventListener('dragleave', function () { card.classList.remove('drag-over'); });
      card.addEventListener('drop', function (e) {
        e.preventDefault();
        card.classList.remove('drag-over');
        var studentId = e.dataTransfer.getData('text/plain');
        if (studentId) moveStudent(studentId, g.id);
      });

      board.appendChild(card);
    });
  }

  function renderMember(m, group) {
    var row = document.createElement('div');
    row.className = 'sg-member' + (m.is_leader ? ' is-leader' : '');
    row.draggable = true;
    row.setAttribute('data-student-id', m.student_id);
    row.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('text/plain', String(m.student_id));
    });

    var nm = document.createElement('span');
    nm.className = 'nm';
    nm.innerHTML = (m.is_leader ? '<span class="crown">&#9733;</span> ' : '') +
      esc(m.name) + '<span class="avg">' + esc(fmtAvg(m.basis_average)) + '</span>';
    row.appendChild(nm);

    if (!m.is_leader) {
      var leaderBtn = document.createElement('button');
      leaderBtn.type = 'button';
      leaderBtn.className = 'sg-leader-btn';
      leaderBtn.title = 'Make group leader';
      leaderBtn.textContent = 'Lead';
      leaderBtn.addEventListener('click', function () {
        post(DATA.urls.leader, { group_id: group.id, student_id: m.student_id }).then(function (res) {
          if (res.ok) { DATA = res.data; render(); }
          else alert(res.error || 'Could not set leader.');
        });
      });
      row.appendChild(leaderBtn);
    }

    var moveSelect = document.createElement('select');
    moveSelect.className = 'sg-move-select';
    var optMove = document.createElement('option');
    optMove.textContent = 'Move to...';
    optMove.value = '';
    moveSelect.appendChild(optMove);
    DATA.groups.forEach(function (g2) {
      if (g2.id === group.id) return;
      var opt = document.createElement('option');
      opt.value = g2.id;
      opt.textContent = g2.label;
      moveSelect.appendChild(opt);
    });
    moveSelect.addEventListener('change', function () {
      if (moveSelect.value) moveStudent(m.student_id, moveSelect.value);
    });
    row.appendChild(moveSelect);

    return row;
  }

  function moveStudent(studentId, groupId) {
    post(DATA.urls.move, { student_id: studentId, group_id: groupId }).then(function (res) {
      if (res.ok) { DATA = res.data; render(); }
      else alert(res.error || 'Could not move student.');
    });
  }

  render();

  var exportBtn = document.getElementById('sgExportPng');
  if (exportBtn && window.html2canvas) {
    exportBtn.addEventListener('click', function () {
      var node = document.getElementById('sgBoardWrap');
      window.html2canvas(node, { scale: 2, backgroundColor: '#ffffff', useCORS: true }).then(function (canvas) {
        var a = document.createElement('a');
        a.download = (DATA.title || 'study-groups').replace(/[^a-z0-9-_]+/gi, '-') + '.png';
        a.href = canvas.toDataURL('image/png');
        a.click();
      });
    });
  }
})();
