/**
 * ActiTrack 使用者資料同步模組
 * 【功能】從伺服器取得使用者名稱，並更新頁面上標記為 data-user-field="username" 的元素
 */

const USER_CONFIG_URL = '/api/user_config'; // 後端使用者設定的 API 端點

class UserSync {
    constructor() {
        this.username = "WebUser"; // 從伺服器取得前的預設顯示名稱
    }

    // 向伺服器取得最新使用者名稱並更新 UI
    async init() {
        try {
            const res  = await fetch(USER_CONFIG_URL);
            const data = await res.json();
            this.username = data.username;
            this.updateUI();
        } catch (e) {
            console.error("無法載入使用者設定:", e);
            // 失敗時維持預設值顯示，不影響頁面運作
        }
    }

    // 更新所有帶有 data-user-field="username" 屬性的元素
    // 以 data-* 屬性選取目標，比 class/id 更語意清晰
    updateUI() {
        document.querySelectorAll('[data-user-field="username"]').forEach(el => {
            el.textContent = this.username;
        });
    }

    // 供其他模組取得目前使用者名稱（如儲存紀錄時附帶）
    getCurrentUsername() {
        return this.username;
    }
}

// 建立全域實例，供其他腳本以 window.userSync.getCurrentUsername() 存取
window.userSync = new UserSync();
document.addEventListener('DOMContentLoaded', () => window.userSync.init());
