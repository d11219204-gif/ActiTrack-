/**
 * ActiTrack UI 控制器
 * 【功能】主頁面的視覺操作核心：側邊欄開關、子選單動畫、運動選單、防閃爍初始化
 */
class ActiTrackUI {
    // 頁面載入完成後呼叫的入口點
    static init() {
        this.initSidebarResizer();
        
        if (!window.actiTrack) window.actiTrack = new ActiTrackAPI();
        if (document.getElementById('submenu1')) {
            window.actiTrack.loadSportsMenu('submenu1'); // 向後端取得最新選單
        }
    }

    // 切換側邊欄顯示/隱藏
    static toggleSidebar() {
        const sidebar    = document.getElementById('sidebar');
        const restoreBtn = document.getElementById('restore-btn');
        if (!sidebar || !restoreBtn) return;

        sidebar.classList.toggle('hidden');
        if (sidebar.classList.contains('hidden')) {
            setTimeout(() => restoreBtn.classList.add('visible'), 300);
        } else {
            restoreBtn.classList.remove('visible');
        }
    }

    // 切換子選單展開/收合（max-height 動畫）並記錄狀態至 localStorage
    static toggleSubmenu(id) {
        const sm   = document.getElementById(id);
        const icon = document.getElementById(id === 'submenu1' ? 'icon1' : 'icon2');
        if (!sm || !icon) return;
        
        // 只有使用者手動點擊時才加動畫（頁面初始化時以 instantRestore 無動畫還原）
        sm.style.transition = 'max-height 0.3s ease-in-out';
        sm.classList.toggle('collapsed');
        
        if (sm.classList.contains('collapsed')) {
            icon.classList.remove('rotated');
            localStorage.setItem('actitrack_' + id, 'closed');
        } else {
            icon.classList.add('rotated');
            localStorage.setItem('actitrack_' + id, 'open');
        }
    }

    // 初始化側邊欄的拖曳調整寬度功能
    static initSidebarResizer() {
        const resizer = document.getElementById('resizer');
        const sidebar = document.getElementById('sidebar');
        if (!resizer || !sidebar) return;

        let isResizing = false;
        
        resizer.addEventListener('mousedown', () => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            sidebar.style.transition   = 'none'; // 拖曳中停用動畫
            resizer.classList.add('active');
        });
        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            let p = (e.clientX / window.innerWidth) * 100;
            if (p < 10) p = 10;
            if (p > 50) p = 50;
            sidebar.style.flex  = `0 0 ${p}%`;
            sidebar.style.width = `${p}%`;
        });
        document.addEventListener('mouseup', () => {
            if (!isResizing) return;
            isResizing                 = false;
            document.body.style.cursor = 'default';
            sidebar.style.transition   = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
            resizer.classList.remove('active');
        });
    }
}

// 將方法掛載至 window，讓 HTML 的 onclick 屬性可以直接呼叫
window.toggleSidebar  = () => ActiTrackUI.toggleSidebar();
window.toggleSubmenu  = (id) => ActiTrackUI.toggleSubmenu(id);
// 切換運動模式：修改 URL 的 ?mode= 參數，後端依此決定使用哪個偵測模型
window.startSpecificSport = (modeName) => {
    window.location.href = `ActiTrack_Detect.html?mode=${modeName}`;
};

// ==========================================
// 防閃爍機制（Instant Restore）
// 問題：等待 DOMContentLoaded 才還原狀態，頁面切換時會有一瞬間跳動
// 解法：腳本載入時立即（同步）還原，transition:none 確保無動畫、無閃爍
// ==========================================
(function instantRestore() {
    // Step 1：從快取立即填入選單內容（不等 API 回應）
    const submenu1 = document.getElementById('submenu1');
    if (submenu1) {
        const cachedString = localStorage.getItem('actitrack_sports_menu_cache');
        if (cachedString) {
            try {
                const menuData     = JSON.parse(cachedString);
                const isDetectPage = window.location.pathname.includes('ActiTrack_Detect.html');
                const currentMode  = new URLSearchParams(window.location.search).get('mode') || 'auto';
                
                let html = '';
                menuData.forEach(item => {
                    const activeClass = (isDetectPage && item.class_name === currentMode) ? 'active' : '';
                    html += `<div class="submenu-item ${activeClass}" onclick="startSpecificSport('${item.class_name}')">${item.display_name}</div>`;
                });
                submenu1.innerHTML = html;
            } catch (e) { console.error("選單快取解析失敗", e); }
        }
    }

    // Step 2：無動畫地還原各子選單的展開/收合狀態
    ['submenu1', 'submenu2'].forEach(id => {
        const savedState = localStorage.getItem('actitrack_' + id);
        const sm   = document.getElementById(id);
        const icon = document.getElementById(id === 'submenu1' ? 'icon1' : 'icon2');
        
        if (sm && icon) {
            sm.style.transition = 'none'; // 關閉動畫，防止頁面載入時的閃爍
            
            if (savedState === 'open') {
                sm.classList.remove('collapsed');
                icon.classList.add('rotated');
            } else {
                sm.classList.add('collapsed');
                icon.classList.remove('rotated');
            }
            
            // 50ms 後重新啟用動畫（此時初始渲染已完成，使用者不會看到跳動）
            setTimeout(() => { sm.style.transition = 'max-height 0.3s ease'; }, 50);
        }
    });
})(); // IIFE：定義後立即執行

// DOM 就緒後啟動其餘 UI 功能（需要 DOM 才能執行的部分）
document.addEventListener('DOMContentLoaded', () => {
    ActiTrackUI.init();
});
