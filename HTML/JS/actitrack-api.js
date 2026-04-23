/**
 * ActiTrack API 客戶端
 * 負責與 server.py 溝通，統一管理影像串流與數據更新
 */
const API_CONFIG = {
    statusEndpoint: '/api/status',          // 獲取當前偵測狀態的 API 端點
    videoEndpoint: '/video_feed',           // 獲取影像串流的 API 端點
    skeletonEndpoint: '/api/toggle_skeleton',// 切換骨架顯示的 API 端點
    stopEndpoint: '/api/stop',              // 停止偵測並存檔的 API 端點
    menuEndpoint: '/api/sports_menu',       // 獲取動態運動選單的 API 端點
    updateInterval: 150,                     // 狀態更新的輪詢間隔時間 (毫秒)
};

class ActiTrackAPI {
    /**
     * 初始化 ActiTrack API 實例
     */
    constructor() {
        this.intervalId = null;     // 儲存狀態輪詢的計時器 ID
        this.isSwitching = false;   // 標記是否正在切換運動模式
        
        // 當使用者關閉視窗或離開頁面時，強制通知後端停止偵測並釋放資源
        window.addEventListener('beforeunload', () => this.forceStop());
        window.addEventListener('pagehide', () => this.forceStop());
    }

    /**
     * 從後端獲取運動項目並載入左側選單
     * @param {string} containerId - 欲渲染選單的 HTML 容器 ID
     */
    async loadSportsMenu(containerId) {
        try {
            const container = document.getElementById(containerId);
            if (!container) return; // 若找不到容器則退出
            
            // 呼叫 API 獲取運動選單資料
            const res = await fetch(API_CONFIG.menuEndpoint);
            if (!res.ok) return;
            const menuData = await res.json();
            
            // 取得網址列上的 mode 參數，用來判斷當前模式 (預設 auto)
            const urlParams = new URLSearchParams(window.location.search);
            const currentMode = urlParams.get('mode') || 'auto';
            // 判斷當前是否處於 Detect (偵測) 頁面
            const isDetectPage = window.location.pathname.includes('ActiTrack_Detect.html');
            
            let html = '';

            // 只有在 Detect 頁面時，才會針對當前選擇的模式加上 active (深色高亮) 樣式
            const autoActiveClass = (isDetectPage && currentMode === 'auto') ? ' active' : '';
            html += `<div class="submenu-item${autoActiveClass}" onclick="startSpecificSport('auto')">自動偵測模式</div>`;
            
            // 遍歷所有運動項目，動態生成子選單
            menuData.forEach(item => {
                const activeClass = (isDetectPage && currentMode === item.class_name) ? ' active' : '';
                html += `<div class="submenu-item${activeClass}" onclick="startSpecificSport('${item.class_name}')">${item.display_name}</div>`;
            });
            container.innerHTML = html;

            // 檢查 localStorage，判斷先前選單是否為展開狀態
            const savedState = localStorage.getItem('actitrack_' + containerId);
            if (savedState === 'open') {
                // 若為展開狀態，暫時移除動畫以防止載入閃爍，再恢復展開
                container.style.transition = 'none'; 
                container.classList.remove('collapsed');
                void container.offsetHeight; // 強制觸發重繪 (Reflow)
                container.style.transition = 'max-height 0.3s ease-in-out'; 
            }        
        } catch (e) {
            console.error("載入選單失敗", e);
        }
    }

    /**
     * 開始接收影像串流並監控數據更新
     * @param {Object} elements - 包含需更新之 DOM 元素 ID 的物件
     */
    startMonitoring(elements) {
        this.currentElements = elements; // 紀錄當前綁定的 UI 元素
        
        // 清除現有的計時器，避免重複輪詢
        if (this.intervalId) clearInterval(this.intervalId);
        
        // 設定影像串流來源 (加上時間戳 t 避免瀏覽器快取舊畫面)
        const videoEl = document.getElementById(elements.videoId);
        if (videoEl) {
            videoEl.src = `${API_CONFIG.videoEndpoint}?t=${new Date().getTime()}`;
        }

        // 設定定時器，定期向後端要求最新的狀態資料
        this.intervalId = setInterval(async () => {
            try {
                const res = await fetch(API_CONFIG.statusEndpoint);
                if (!res.ok) return;
                const data = await res.json();
                
                // 使用獲取的資料更新 UI
                this._updateUI(data, elements);
            } catch (e) {
                // 忽略網路小錯誤 (例如瞬間斷線)
            }
        }, API_CONFIG.updateInterval);
    }

    /**
     * 內部方法：將後端回傳的狀態資料更新到畫面上
     * @param {Object} data - 後端回傳的偵測資料
     * @param {Object} elements - UI 元素 ID 對應表
     */
    _updateUI(data, elements) {
        // 更新當前鎖定(執行中)的運動模式名稱 (例如: 深蹲)
        if (elements.modeId) {
            const modeEl = document.getElementById(elements.modeId);
            if (modeEl) modeEl.textContent = data.locked_mode;
        }
        
        // 👇 新增這段邏輯，讓 status-box 也能同步顯示運動名稱 👇
        if (elements.statusId) {
            const statusEl = document.getElementById(elements.statusId);
            if (statusEl) statusEl.textContent = data.locked_mode;
        }
        // 👆 新增結束 👆

        // 更新主要計數 (次數或距離)
        if (elements.countId) {
            const countEl = document.getElementById(elements.countId);
            if (countEl) countEl.textContent = data.main_count;
        }
        
        // 更新錯誤次數
        if (elements.badCountId) {
            const badCountEl = document.getElementById(elements.badCountId);
            if (badCountEl) badCountEl.textContent = data.main_wrong;
        }
        
        // 重新渲染右下角詳細的參數面板
        if (elements.panelId) {
            const panelEl = document.getElementById(elements.panelId);
            if (panelEl) panelEl.innerHTML = this._buildPanel(data.details);
        }
    }

    /**
     * 內部方法：建構右下方數據面板的 HTML
     * @param {Array} details - 所有偵測器的詳細資料陣列
     * @returns {string} 組合好的 HTML 字串
     */
    _buildPanel(details) {
        const urlParams = new URLSearchParams(window.location.search);
        const currentMode = urlParams.get('mode') || 'auto';
        
        // 依照當前模式過濾要在面板上顯示的運動項目
        const filteredDetails = details.filter(item => {
            if (currentMode === 'auto') return true; // 自動模式顯示所有活躍的偵測器
            return item.class_name === currentMode;  // 單一模式只顯示該指定的偵測器
        });

        // 尚未載入完成或無資料時的提示
        if (filteredDetails.length === 0) {
            return '<div class="loading-text">載入偵測模組中...</div>';
        }

        // 面板標題列結構
        let html = `<div class="param-list">
            <div class="param-row header">
                <div class="param-name">運動項目</div>
                <div class="param-correct">正確</div>
                <div class="param-wrong">錯誤</div>
            </div>`;

        // 遍歷每個偵測器生成對應的數據列
        filteredDetails.forEach(item => {
            let rowClass = 'param-row';
            
            // 根據偵測器狀態給予不同的 CSS class
            if (item.locked) {
                rowClass += ' locked';    // 代表當前正在執行的運動 (高亮)
            } else if (!item.active) {
                rowClass += ' inactive';  // 代表已排除或暫時不活躍的運動 (灰暗)
            }

            // 區分是跑步類(距離)還是次數類(計次)
            const correctDisplay = item.is_running ? `${item.value}m` : item.correct;
            const wrongDisplay = item.is_running ? '-' : item.wrong; // 跑步無錯誤次數，顯示 '-'

            html += `
                <div class="${rowClass}">
                    <div class="param-name" title="${item.label}">${item.label}</div>
                    <div class="param-correct">${correctDisplay}</div>
                    <div class="param-wrong">${wrongDisplay}</div>
                </div>`;
        });
        
        return html + '</div>';
    }

    /**
     * 切換畫面上的骨架顯示
     * @param {boolean} enable - true 顯示，false 隱藏
     */
    toggleSkeleton(enable) {
        fetch(`${API_CONFIG.skeletonEndpoint}?enable=${enable}`, { method: 'POST' }).catch(()=>{});
    }

    /**
     * 停止監控與更新數據
     */
    stopMonitoring() {
        if (this.intervalId) clearInterval(this.intervalId); // 停止定時更新
        this.forceStop(); // 通知後端停止並存檔
    }

    /**
     * 強制停止後端偵測，主要在離開頁面時調用以確保存檔與資源釋放
     */
    forceStop() {
        try { 
            // 優先使用 sendBeacon，確保網頁關閉時仍能送出請求
            navigator.sendBeacon(API_CONFIG.stopEndpoint); 
        } 
        catch (e) { 
            // 若不支援 sendBeacon，改用 fetch 並設定 keepalive
            fetch(API_CONFIG.stopEndpoint, { method: 'POST', keepalive: true }).catch(()=>{}); 
        }
    }
}

// 暴露出全域類別
window.ActiTrackAPI = ActiTrackAPI;

// 建立全域唯一的 actiTrack 實例 (單例模式)，供所有頁面直接呼叫
if (!window.actiTrack) {
    window.actiTrack = new ActiTrackAPI();
}