'use strict';

(function () {
    const APP_ID = 'rpa4all_admin_actions';

    // Seletores que o Nextcloud 33 usa na página /settings/users (Vue SPA)
    const ROW_SELECTORS = [
        '[data-cy="user-list"] tr',
        '.user-list-grid tr',
        '#app-content tr[data-id]',
        '.active-user-list tr',
    ];

    function getUserIdFromRow(row) {
        // NC 33: data-id ou data-user no <tr>, ou texto da primeira célula
        const direct = row.dataset.id || row.dataset.user;
        if (direct) return direct;

        // Fallback: primeira célula tem o username
        const cell = row.querySelector('td:first-child, .cell-displayname, .user-name');
        return cell ? cell.textContent.trim() : null;
    }

    function callAction(action, userId, btn) {
        const url = OC.generateUrl('/apps/' + APP_ID + '/api/users/' + encodeURIComponent(userId) + '/' + action);
        btn.disabled = true;
        btn.classList.add('rpa4all-loading');

        fetch(url, {
            method: 'POST',
            headers: {
                'requesttoken': OC.requestToken,
                'Content-Type': 'application/json',
            },
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                OC.Notification.showTemporary(data.message, { type: 'success' });
            } else {
                OC.Notification.showTemporary((data.error || 'Erro desconhecido'), { type: 'error' });
            }
        })
        .catch(() => {
            OC.Notification.showTemporary('Erro de comunicação com o servidor', { type: 'error' });
        })
        .finally(() => {
            btn.disabled = false;
            btn.classList.remove('rpa4all-loading');
        });
    }

    function injectButtons(row) {
        if (row.querySelector('.rpa4all-actions')) return; // já injetado

        const userId = getUserIdFromRow(row);
        if (!userId) return;

        // Procurar última célula ou criar container
        let lastCell = row.querySelector('td:last-child, .cell-actions');
        if (!lastCell) return;

        const wrap = document.createElement('span');
        wrap.className = 'rpa4all-actions';

        const reloginBtn = document.createElement('button');
        reloginBtn.className = 'rpa4all-btn rpa4all-btn-relogin';
        reloginBtn.title = 'Revogar tokens e forçar re-login via Authentik';
        reloginBtn.textContent = '🔄 Re-Login';
        reloginBtn.addEventListener('click', e => {
            e.stopPropagation();
            if (confirm('Forçar re-login de "' + userId + '"?\nTodos os tokens e sessões serão revogados.')) {
                callAction('relogin', userId, reloginBtn);
            }
        });

        const scanBtn = document.createElement('button');
        scanBtn.className = 'rpa4all-btn rpa4all-btn-scan';
        scanBtn.title = 'Forçar re-scan de arquivos do usuário no servidor';
        scanBtn.textContent = '🗂️ Forçar Sync';
        scanBtn.addEventListener('click', e => {
            e.stopPropagation();
            callAction('scan', userId, scanBtn);
        });

        wrap.appendChild(reloginBtn);
        wrap.appendChild(scanBtn);
        lastCell.appendChild(wrap);
    }

    function scanTable() {
        for (const sel of ROW_SELECTORS) {
            document.querySelectorAll(sel).forEach(row => injectButtons(row));
        }
    }

    function init() {
        scanTable();

        // Observar mudanças no SPA Vue para reinjetar quando a lista atualizar
        const root = document.getElementById('app-content') || document.body;
        const observer = new MutationObserver(() => scanTable());
        observer.observe(root, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
