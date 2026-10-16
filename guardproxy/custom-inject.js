// === Auth LT translations ===
(function () {
    // Branding is per-deployment: name + logo come from /_gp/brand.json, which is
    // NOT in the repo (gitignored, created by the installer). Keeps customer names
    // and logos out of the published repository. Falls back to neutral defaults.
    var BRAND = { name: 'GuardPrompt', logo: '' };

    fetch('/_gp/brand.json', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (b) {
            if (b && typeof b === 'object') {
                if (b.name) BRAND.name = b.name;
                if (b.logo) BRAND.logo = b.logo;
                applyAuthLt();
            }
        })
        .catch(function () { /* no brand.json -> defaults */ });

    function applyAuthLt() {
        var title = 'Open WebUI - ' + BRAND.name;
        if (document.title !== title) {
            document.title = title;
        }

        if (window.location.pathname !== '/auth') return;

        // 1. VERTIMAI: Bendri tekstai ir logotipas
        document.querySelectorAll('h1,h2,h3,div,span,p').forEach(function(el){
            if ((el.textContent || '').trim() === 'Sign in to Open WebUI with LDAP' && el.children.length === 0) {
                el.textContent = 'Dirbtinio intelekto asistentas';
                if (BRAND.logo && !document.getElementById('client-logo')) {
                    var rimg = document.createElement('img');
                    rimg.id = 'client-logo';
                    rimg.src = BRAND.logo;
                    rimg.style = 'height:60px;width:auto;display:block;margin:0 auto 20px auto;';
                    el.parentNode.insertBefore(rimg, el);
                }
            }
        });

        document.querySelectorAll('label').forEach(function(el){
            var t = (el.textContent || '').trim();
            if (t === 'Username') el.textContent = 'Naudotojo vardas';
            if (t === 'Password') el.textContent = 'Slaptažodis';
            if (t === 'Email') el.textContent = 'El. paštas';
        });

        document.querySelectorAll('input').forEach(function(el){
            var p = el.getAttribute('placeholder') || '';
            if (p === 'Enter Your Username') el.setAttribute('placeholder', 'Įveskite naudotojo vardą');
            if (p === 'Enter Your Password') el.setAttribute('placeholder', 'Įveskite slaptažodį');
            if (p === 'Enter Your Email') el.setAttribute('placeholder', 'Įveskite el. paštą');
        });

        document.querySelectorAll('button').forEach(function(el){
            var t = (el.textContent || '').trim();
            if (t === 'Authenticate') el.textContent = 'Prisijungti';
            if (t === 'Sign in') el.textContent = 'Prisijungti';
            
            // 2. SAUGUS PASLĖPIMAS: Surandame tikslų registracijos mygtuką ir paslepiame jo mt-4 bloką
            if (t === 'Sukurti paskyrą' || t === 'Sign up') {
                var parentDiv = el.parentElement;
                if (parentDiv && parentDiv.classList.contains('text-center') && parentDiv.textContent.includes('Neturite paskyros?')) {
                    parentDiv.style.setProperty('display', 'none', 'important');
                }
            }
        });

        // 3. DINAMINIS MYGTUKŲ KEITIMAS: LDAP <-> El. paštas
        document.querySelectorAll('a,button,div,span,p').forEach(function(el){
            var t = (el.textContent || '').trim();
            
            if (el.children.length === 0) {
                if (t === 'Continue with Username') el.textContent = 'Tęsti su vartotojo vardu';

                var isEmailFormActive = document.querySelector('input[type="email"]') !== null;

                if (t === 'Continue with Email' || t === 'Tęsti su el. paštu' || t === 'Continue with LDAP' || t === 'Tęsti su LDAP') {
                    if (isEmailFormActive) {
                        if (el.textContent !== 'Tęsti su LDAP') el.textContent = 'Tęsti su LDAP';
                    } else {
                        if (el.textContent !== 'Tęsti su el. paštu') el.textContent = 'Tęsti su el. paštu';
                    }
                }
            }
        });

        // 4. SUTIKIMO PRIERAŠAS (BDAR 13/14 str. + DI aktas): po prisijungimo
        //    mygtuku (ir po nekeičiamu elementu žemiau jo), formos apačioje.
        //    Dvi ATSKIROS nuorodos — URL'us pakoreguok žemiau (TODO).
        var GP_TERMS_URL   = '#';   // TODO: „DI asistento naudojimo taisyklių" URL
        var GP_PRIVACY_URL = '#';   // TODO: „privatumo politikos" URL
        if (!document.getElementById('gp-consent')) {
            var _btn = Array.prototype.slice.call(document.querySelectorAll('button'))
                .filter(function (b) {
                    return ['Prisijungti', 'Authenticate', 'Sign in']
                        .indexOf((b.textContent || '').trim()) !== -1;
                })[0];
            var _anchor = (_btn && _btn.closest('form')) ||
                          document.querySelector('form') ||
                          (_btn && _btn.parentElement);
            if (_anchor) {
                var _c = document.createElement('div');
                _c.id = 'gp-consent';
                _c.style.cssText = 'margin-top:16px;text-align:center;font-size:12px;' +
                    'line-height:1.5;color:#888;';
                _c.innerHTML = 'Prisijungdami sutinkate su ' +
                    '<a href="' + GP_TERMS_URL + '" target="_blank" rel="noopener" ' +
                    'style="color:inherit;text-decoration:underline;">DI asistento naudojimo taisyklėmis</a>' +
                    ' ir ' +
                    '<a href="' + GP_PRIVACY_URL + '" target="_blank" rel="noopener" ' +
                    'style="color:inherit;text-decoration:underline;">privatumo politika</a>.';
                _anchor.appendChild(_c);
            }
        }
    }

    applyAuthLt();
    requestAnimationFrame(applyAuthLt);
    var mo = new MutationObserver(function() { applyAuthLt(); });
    if (document.body) {
        mo.observe(document.body, { childList: true, subtree: true });
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            applyAuthLt();
            mo.observe(document.body, { childList: true, subtree: true });
        });
    }
})();

// === GuardPrompt Logo Injection ===
(function(){
    const LOGO_ID = 'guardprompt-logo';
    const HTML = '<div id="guardprompt-logo" style="display:flex;align-items:center;margin-right:6px;"><a href="https://guardprompt.lt" target="_blank" style="opacity:0.95;"><img src="/_gp/GuardPrompt.png" style="height:22px;width:auto;"></a></div>';
    function place() {
        const right = document.querySelector('div.self-end.flex.space-x-1.mr-1.shrink-0');
        if (!right) return;
        if (!document.getElementById(LOGO_ID)) {
            right.insertAdjacentHTML('beforebegin', HTML);
        }
    }
    // Ištaisyta sintaksės klaida čia:
    [200, 400, 800, 1500, 2500].forEach(function(t){ setTimeout(place, t); });
    new MutationObserver(place).observe(document.body, { childList:true, subtree:true });
})();

// === Susitikimų protokolas — mic button in the top bar ===
// Opens /_gp/protokolas.html (served by guardproxy, same origin -> OWUI auth
// cookie carries over, no key needed). Placed next to the GuardPrompt logo,
// using the same toolbar anchor so it survives OWUI's SPA re-renders.
(function(){
    const BTN_ID = 'gp-protokolas-btn';
    const URL = '/_gp/protokolas.html';
    const TITLE = 'Susitikimų protokolas — įrašyti ir transkribuoti';
    const HTML =
        '<button id="' + BTN_ID + '" title="' + TITLE + '" type="button" ' +
        'style="display:flex;align-items:center;justify-content:center;margin-right:6px;' +
        'height:30px;width:30px;padding:0;border:none;background:transparent;cursor:pointer;' +
        'border-radius:8px;color:currentColor;opacity:0.85;">' +
        '<svg xmlns="http://www.w3.org/2000/svg" width="19" height="19" viewBox="0 0 24 24" ' +
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>' +
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>' +
        '<line x1="12" y1="19" x2="12" y2="23"></line>' +
        '<line x1="8" y1="23" x2="16" y2="23"></line>' +
        '</svg></button>';
    function place() {
        const right = document.querySelector('div.self-end.flex.space-x-1.mr-1.shrink-0');
        if (!right) return;
        if (document.getElementById(BTN_ID)) return;
        right.insertAdjacentHTML('beforebegin', HTML);
        const btn = document.getElementById(BTN_ID);
        if (btn) {
            btn.addEventListener('mouseenter', function(){ btn.style.opacity = '1'; });
            btn.addEventListener('mouseleave', function(){ btn.style.opacity = '0.85'; });
            btn.addEventListener('click', function(){ window.open(URL, '_blank', 'noopener'); });
        }
    }
    [200, 400, 800, 1500, 2500].forEach(function(t){ setTimeout(place, t); });
    new MutationObserver(place).observe(document.body, { childList:true, subtree:true });
})();

// === Model-switch guard ===
// OWUI keeps the whole chat context on a mid-chat model switch and does NOT reset
// per-model tools/knowledge/features. So switching e.g. REGITRA (legacy KB) -> a
// web model mid-conversation makes the new model answer from the previous model's
// injected KB / wrong feature state ("uses local DB instead of searching the web").
// There is no OWUI setting to reload a model fresh on switch. Fix: when the model
// changes INSIDE an existing chat, open a NEW chat with the newly chosen model
// (/?models=<id>), so it starts clean with its own KB/web/terminal/prompt.
//
// Detection is robust against SPA re-renders: the model button carries
// aria-label="Selected model: <NAME>"; an existing conversation is at /c/<id>
// (a brand-new/empty chat is at "/", so we never fire before the first message).
(function(){
    var PREFIX = 'Selected model: ';
    var lastCid = null, lastModel = null;
    var idByName = {};

    function loadMap(){
        fetch('/api/models', { credentials: 'same-origin' })
            .then(function(r){ return r.ok ? r.json() : null; })
            .then(function(j){
                var arr = (j && (j.data || j)) || [];
                arr.forEach(function(m){
                    if (m && m.id) { idByName[m.id] = m.id; if (m.name) idByName[m.name] = m.id; }
                });
            })
            .catch(function(){});
    }
    loadMap();

    function currentModel(){
        var b = document.querySelector('button[aria-label^="' + PREFIX + '"]');
        if (!b) return null;
        var v = (b.getAttribute('aria-label') || '').slice(PREFIX.length).trim();
        return v || null;
    }
    function chatId(){
        var m = location.pathname.match(/^\/c\/([0-9a-fA-F-]+)/);
        return m ? m[1] : null;   // null => "/" i.e. a new/empty chat
    }
    function toast(txt){
        try{
            var d = document.createElement('div');
            d.textContent = txt;
            d.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);' +
                'z-index:2147483647;background:#1f2933;color:#fff;padding:12px 18px;border-radius:12px;' +
                'font:500 14px system-ui,-apple-system,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.28);' +
                'max-width:92vw;text-align:center;line-height:1.4;';
            document.body.appendChild(d);
            setTimeout(function(){ try{ d.remove(); }catch(e){} }, 3500);
        }catch(e){}
    }

    function check(){
        var cid = chatId();
        var model = currentModel();
        if (model === null) return;                 // selector not mounted yet
        // Different chat (opened/switched chat, or landed on a new one) -> re-baseline,
        // never treat as a mid-chat switch.
        if (cid !== lastCid) { lastCid = cid; lastModel = model; return; }
        if (model === lastModel) return;            // nothing changed
        var prev = lastModel;
        lastModel = model;
        if (!prev) return;                          // first observation
        if (!cid) return;                           // only inside an existing /c/ chat
        // -> user switched model in the middle of a conversation.
        var id = idByName[model] || model;
        toast('🔄 Atidaromas naujas pokalbis su „' + model + '" — kad įrankiai (web paieška, ' +
              'žinių bazė, terminalas) veiktų teisingai su pasirinktu modeliu.');
        setTimeout(function(){
            try { location.assign('/?models=' + encodeURIComponent(id)); }
            catch(e){ location.href = '/?models=' + encodeURIComponent(id); }
        }, 1100);
    }

    function start(){
        try{
            new MutationObserver(check).observe(document.body, {
                childList: true, subtree: true, attributes: true, attributeFilter: ['aria-label']
            });
        }catch(e){}
    }
    if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
    setInterval(check, 1200);   // backstop: catches attribute swaps the observer may miss
})();
