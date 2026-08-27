(function () {
  "use strict";
  const CONSTANTS = {
    VALID_TOASTER_TYPES: [
      "success", "error", "info", "warning"
    ],
    INVALID_TYPE: "Invalid toaster type"
  }
  /**
   * @desc html body of the toaster
   * @returns {html}
   */
  function getToasterHTML() {
    return `<div class="toaster show"><div id="alert-bg" class="fy-toast" role="alert" aria-live="assertive" aria-atomic="true" data-delay="2000">
      <button type="button" class="ml-2 mb-1 close" data-dismiss="fy-toast" aria-label="Close">
        <span aria-hidden="true">&times;</span>
      </button>
      <div class="fy-toast-body">
       <h4 id="title"></h4>
       <p id="desc"></p>
       <p id="desc_sub"></p>
      </div>
    </div></div>`;
  }
  /**
   * @desc setting toaster info in toaster body
   * @returns {void}
   */
  function displayItem(config, title, desc, desc_sub) {
    var alert_type = config.type;
    var classname = "fy-" + alert_type;
    $("#alert-bg")
      .addClass(classname + " show")
      .fadeIn();
    title.innerText = config.title ? config.title : null;
    desc.innerText = config.desc ? config.desc : null;
    desc_sub.innerText = config.desc_sub ? config.desc_sub : null;
    $(".fy-toast,.fy-toast p,.fy-toast h4 ").removeAttr("id");
    $(".toaster").addClass("show");
  }
  /**
   * A function to render toaster
   * @param {object} config 
   * @param {int} autoClose 
   * @return {promise}
   */
  window.FyersToaster = function(config, AUTO_CLOSE = 5000) {
    return new Promise(function(resolve, reject) {
      if (CONSTANTS.VALID_TOASTER_TYPES.includes(config.type)) {
        var timeout_id = null;
        $(".toaster").removeClass("show");
        var body = document.querySelector("body");
        if (!$("#toaster").length) {
          var toaster = document.createElement("div");
          toaster.setAttribute("id", "toaster");
          toaster.setAttribute("class", "");
          body.appendChild(toaster);
        }
        $("#toaster").prepend(getToasterHTML());
        var title = document.getElementById("title");
        var desc = document.getElementById("desc");
        var desc_sub = document.getElementById("desc_sub");
        displayItem(config, title, desc, desc_sub);
  
        $(".close").on("click", function () {
          $(this).parent(".fy-toast").parent(".toaster").remove();
        });
        if (timeout_id) {
          clearTimeout(timeout_id);
        }
        timeout_id = setTimeout(function () {
          $(".toaster").last().remove();
        }, AUTO_CLOSE);
      } else {
        reject(CONSTANTS.INVALID_TYPE)
      }
    })    
  }
})();
