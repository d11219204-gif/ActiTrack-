// ActiTrack_User_Sync.js
// 【功能】全頁面共用的使用者資料同步模組
// 採「兩段式同步」：先以 localStorage 快取即時顯示（防閃爍），再背景比對伺服器資料

// 將使用者資料實際套用至頁面各元素的純渲染函式
function applyUserData(username, avatarShape, cacheTime, fontScale) {
    // 1. 同步暱稱至所有 .user-name 元素，以及設定頁的輸入框
    document.querySelectorAll('.user-name').forEach(el => { el.innerText = username; });
    const nameInput = document.getElementById('user-name-input');
    if (nameInput && nameInput.value !== username) nameInput.value = username;

    // 2. 同步頭像形狀下拉選單（僅設定頁存在）
    const shapeSelect = document.getElementById('avatar-shape-select');
    if (shapeSelect) shapeSelect.value = avatarShape;

    // 3. 同步頭像圖片
    // ?t= 時間戳可強制瀏覽器略過快取，重新下載最新圖片
    const avatarUrl    = `/Photo/user_avatar.jpg?t=${cacheTime}`;
    const borderRadius = (avatarShape === 'circle') ? '50%' : '10px'; // 圓形 or 圓角方形

    const avatarIds      = ['sidebar-user-avatar', 'current-avatar'];
    const placeholderIds = ['sidebar-user-placeholder', 'avatar-placeholder'];

    avatarIds.forEach((id, index) => {
        const imgEl         = document.getElementById(id);
        const placeholderEl = document.getElementById(placeholderIds[index]);
        
        if (imgEl) {
            imgEl.style.borderRadius = borderRadius;
            imgEl.style.objectFit   = 'cover';
            if (placeholderEl) placeholderEl.style.borderRadius = borderRadius;

            // 圖片載入失敗時（如尚未上傳）改顯示佔位符
            imgEl.onerror = () => {
                imgEl.style.display = 'none';
                if (placeholderEl) placeholderEl.style.display = 'block';
            };

            imgEl.src           = avatarUrl;
            imgEl.style.display = 'block';
            if (placeholderEl) placeholderEl.style.display = 'none';
        }
    });

    // 4. 套用字體大小（CSS 自訂屬性）並同步設定頁的選單顯示
    if (fontScale) {
        document.documentElement.style.setProperty('--font-scale', fontScale);
        localStorage.setItem('actitrack_font_scale', fontScale);
        
        const select        = document.getElementById('font-scale-select');
        const customWrapper = document.getElementById('custom-scale-wrapper');
        const customInput   = document.getElementById('font-scale-custom');
        if (select && customWrapper && customInput) {
            const presetValues = ["0.8", "1", "1.2", "1.5"];
            if (presetValues.includes(fontScale.toString())) {
                select.value = fontScale.toString();
                customWrapper.style.display = 'none';
            } else {
                select.value = 'custom';
                customWrapper.style.display = 'flex';
                customInput.value = Math.round(fontScale * 100); // 倍率 → 百分比顯示
            }
        }
    }
}

// 主同步函式：先用快取即時渲染，再背景向伺服器確認是否有更新
async function syncUsernameAndAvatar() {
    let localCacheTime = localStorage.getItem('actitrack_avatar_time') || new Date().getTime();
    const cachedData   = JSON.parse(localStorage.getItem('actitrack_user_config') || '{}');
    const savedScale   = localStorage.getItem('actitrack_font_scale') || 1;
    
    // ① 立即使用本機快取渲染，解決切換頁面時的閃爍問題
    applyUserData(
        cachedData.username     || "User",
        cachedData.avatar_shape || "circle",
        localCacheTime,
        cachedData.font_scale   || savedScale
    );

    // ② 背景向伺服器取得最新資料，若有差異則更新快取並重新渲染
    try {
        // ?t= 避免 GET 請求被瀏覽器快取
        const response = await fetch('/api/get_user_config?t=' + new Date().getTime());
        const config   = await response.json();
        
        const serverUpdateTime = config.last_update    || 0;
        const localUpdateTime  = cachedData.last_update || 0;

        // 比對暱稱、頭像形狀、字體大小、更新時間，有任一不同即重新同步
        if (config.username     !== cachedData.username ||
            config.avatar_shape !== cachedData.avatar_shape ||
            config.font_scale   != (cachedData.font_scale || savedScale) ||
            serverUpdateTime    !== localUpdateTime) {
            
            console.log("偵測到遠端資料有更新，重新同步...");
            
            localStorage.setItem('actitrack_user_config', JSON.stringify(config));
            
            // 更新圖片時間戳，強制瀏覽器重新下載頭像
            localCacheTime = new Date().getTime();
            localStorage.setItem('actitrack_avatar_time', localCacheTime);

            applyUserData(
                config.username     || "User",
                config.avatar_shape || "circle",
                localCacheTime,
                config.font_scale   || 1
            );
        }
    } catch (e) {
        console.error("同步失敗:", e); // 失敗時維持快取顯示，不影響使用者
    }
}

// 腳本載入時立即套用字體大小（早於 DOMContentLoaded，確保頁面一出現就是正確大小）
const savedScale = localStorage.getItem('actitrack_font_scale') || 1;
document.documentElement.style.setProperty('--font-scale', savedScale);

document.addEventListener('DOMContentLoaded', syncUsernameAndAvatar);
window.syncUsernameAndAvatar = syncUsernameAndAvatar; // 供其他模組呼叫
