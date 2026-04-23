// actitrack-settings-ui.js
// 【功能】控制設定頁的側邊欄顯示/隱藏，以及拖曳調整寬度功能

// 切換側邊欄顯示，隱藏時延遲顯示還原按鈕（等待 CSS 動畫完成）
function toggleSidebar() {
    const sidebar    = document.getElementById('sidebar');
    const restoreBtn = document.getElementById('restore-btn');
    if (!sidebar || !restoreBtn) return;

    sidebar.classList.toggle('hidden');
    if (sidebar.classList.contains('hidden')) {
        setTimeout(() => restoreBtn.classList.add('visible'), 300); // 動畫結束後才顯示按鈕
    } else {
        restoreBtn.classList.remove('visible');
    }
}

// 切換子選單的展開/收合，並記錄狀態至 localStorage
function toggleSubmenu(id) {
    const sm   = document.getElementById(id);
    const icon = document.getElementById(id === 'submenu1' ? 'icon1' : 'icon2');
    if (!sm || !icon) return;

    if (sm.style.display === 'none' || sm.style.display === '') {
        sm.style.display = 'block';
        icon.classList.add('rotated');
        localStorage.setItem('actitrack_' + id, 'open');
    } else {
        sm.style.display = 'none';
        icon.classList.remove('rotated');
        localStorage.setItem('actitrack_' + id, 'closed');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // 還原上次的子選單展開狀態
    ['submenu1', 'submenu2'].forEach(id => {
        const savedState = localStorage.getItem('actitrack_' + id);
        const sm   = document.getElementById(id);
        const icon = document.getElementById(id === 'submenu1' ? 'icon1' : 'icon2');
        
        if (sm && icon) {
            if (savedState === 'open') {
                sm.style.display = 'block';
                icon.classList.add('rotated');
            } else if (savedState === 'closed') {
                sm.style.display = 'none';
                icon.classList.remove('rotated');
            }
        }
    });

    // 側邊欄拖曳調整寬度
    const resizer = document.getElementById('resizer'); // 邊界拖曳把手元素
    const sidebar = document.getElementById('sidebar');
    if (resizer && sidebar) {
        let isResizing = false;

        resizer.addEventListener('mousedown', () => {
            isResizing = true;
            document.body.style.cursor = 'col-resize'; // 顯示左右拖曳游標
            sidebar.style.transition   = 'none';        // 拖曳中停用動畫
            resizer.classList.add('active');
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            let p = (e.clientX / window.innerWidth) * 100; // 轉換為百分比寬度
            if (p < 10) p = 10; // 最小 10%
            if (p > 50) p = 50; // 最大 50%
            sidebar.style.flex  = `0 0 ${p}%`;
            sidebar.style.width = `${p}%`;
        });

        document.addEventListener('mouseup', () => {
            if (!isResizing) return;
            isResizing                 = false;
            document.body.style.cursor = 'default';
            sidebar.style.transition   = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)'; // 恢復動畫
            resizer.classList.remove('active');
        });
    }
});
