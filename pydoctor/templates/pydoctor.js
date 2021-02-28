// Cookie manipulation functions, from https://www.w3schools.com/js/js_cookies.asp

function setCookie(cname, cvalue, exdays) {
    var d = new Date();
    d.setTime(d.getTime() + (exdays * 24 * 60 * 60 * 1000));
    var expires = "expires="+d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}
  
function getCookie(cname) {
    var name = cname + "=";
    var ca = document.cookie.split(';');
    for(var i = 0; i < ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
        c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
        return c.substring(name.length, c.length);
        }
    }
    return "";
}

// Toogle private view

function initPrivate() {
    var params = (new URL(document.location)).searchParams;
    if (!params || !parseInt(params.get('private'))) {
        var show = false;
        var hash = document.location.hash;
        
        if (hash != '') {
            var anchor = document.querySelector('a[name="' + hash.substring(1) + '"]');
            show = anchor && anchor.parentNode.classList.contains('private');
        }

        var hidden = getCookie("pydoctor-private-hidden");
        if (hidden == "no") {
            show = true;
        }
        if (hidden == ""){
            if (!show) {
                setCookie("pydoctor-private-hidden", "yes", 2);
            }
            else{
                setCookie("pydoctor-private-hidden", "no", 2);
            }
        }

        if (!show) {
            document.body.classList.add("private-hidden");
        }
    }
    updatePrivate();
}

function togglePrivate() {
    // document.body.classList.toggle("private-hidden");
    if (document.body.classList.contains('private-hidden')){
        document.body.classList.remove('private-hidden');
        setCookie("pydoctor-private-hidden", "no", 2);
    }
    else {
        document.body.classList.add("private-hidden");
        setCookie("pydoctor-private-hidden", "yes", 2);
    }
    
    updatePrivate();
}
function updatePrivate() {
    var hidden = document.body.classList.contains('private-hidden');
    document.querySelector('#showPrivate button').innerText =
        hidden ? 'Show Private API' : 'Hide Private API';
    if (history) {
        var search = hidden ? document.location.pathname : '?private=1';
        history.replaceState(null, '', search + document.location.hash);
    }
}

initPrivate();

// Toogle sidebar collapse

function initSideBarCollapse() {
    var collapsed = getCookie("pydoctor-sidebar-collapsed");
    if (collapsed == "yes") {
        document.body.classList.add("sidebar-collapsed");
    }
    if (collapsed == ""){
        setCookie("pydoctor-sidebar-collapsed", "no", 2);
    }
    updateSideBarCollapse();
}

function toggleSideBarCollapse() {
    if (document.body.classList.contains('sidebar-collapsed')){
        document.body.classList.remove('sidebar-collapsed');
        setCookie("pydoctor-sidebar-collapsed", "no", 2);
    }
    else {
        document.body.classList.add("sidebar-collapsed");
        setCookie("pydoctor-sidebar-collapsed", "yes", 2);
    }
    
    updateSideBarCollapse();
}

function updateSideBarCollapse() {
    var collapsed = document.body.classList.contains('sidebar-collapsed');
    document.querySelector('#collapseSideBar a').innerText = collapsed ? '»' : '«';
    document.querySelector('#toggleCollapseSideBar button').innerText = collapsed ? 'Show Sidebar' : 'Hide Sidebar';
}

initSideBarCollapse();
