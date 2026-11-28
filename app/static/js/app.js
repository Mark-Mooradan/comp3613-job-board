const board = document.getElementById("board");

if (board) {
  const role = board.dataset.role;
  const byId = id => document.getElementById(id);
  let jobs = [];
  let editId = null;

  // make elements without inserting raw html
  function element(tag, text, className) {
    const item = document.createElement(tag);
    if (text != null) item.textContent = text;
    if (className) item.className = className;
    return item;
  }

  function message(text, error = false) {
    const box = byId("board-message");
    box.textContent = text;
    box.className = "board-message " + (error ? "error" : "success");
    box.hidden = false;
  }

  async function api(path, method = "GET", data = {}) {
    const options = { method, credentials: "same-origin" };
    if (method !== "GET") {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(data);
    }
    const url = new URL("/api" + path, location.origin);
    const response = await fetch(url, options);
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("Your session may have expired. Please sign in again.");
    }
    const result = await response.json();
    if (!response.ok || result.ok === false) {
      const detail = result.detail || result.error;
      throw new Error(typeof detail === "string" ? detail : "Request failed. Check the entered details.");
    }
    return result;
  }

  // show errors instead of silently failing
  async function run(action) {
    try {
      await action();
    } catch (error) {
      message(error.message, true);
    }
  }

  function button(label, action, style = "") {
    const item = element("button", label, "board-button " + style);
    item.type = "button";
    item.addEventListener("click", async () => {
      item.disabled = true;
      try {
        await run(action);
      } finally {
        item.disabled = false;
      }
    });
    return item;
  }

  function statusBadge(status) {
    const known = ["pending", "published", "submitted", "reviewed", "shortlisted", "hired", "rejected", "withdrawn"];
    return element("span", status || "unknown", "status-badge " + (known.includes(status) ? status : ""));
  }

  function card(title, subtitle, status) {
    const item = element("article", null, "board-card");
    const header = element("div", null, "card-heading");
    header.append(element("h3", title));
    if (status) header.append(statusBadge(status));
    item.append(header);
    if (subtitle) item.append(element("p", subtitle, "card-meta"));
    return item;
  }

  function row() {
    return element("div", null, "button-row");
  }

  function showList(id, items, render, empty) {
    const list = byId(id);
    list.replaceChildren();
    if (items.length === 0) list.append(element("p", empty, "empty-state"));
    else items.forEach(item => list.append(render(item)));
  }

  function safeLink(url) {
    try {
      const link = new URL(url);
      return ["https:", "http:"].includes(link.protocol) ? link.href : null;
    } catch {
      return null;
    }
  }

  function jobCard(job) {
    const item = card(job.title, job.company + " · deadline " + job.deadline, job.status);
    item.append(element("p", job.description, "job-description"));
    return item;
  }

  function applyForm(job) {
    const form = element("form", null, "application-form");
    const letter = element("textarea", null, "form-control");
    letter.id = "letter-" + job.id;
    letter.rows = 3;
    letter.required = true;
    const resume = element("textarea", null, "form-control");
    resume.id = "resume-" + job.id;
    resume.rows = 3;
    const label1 = element("label", "Cover letter", "form-label");
    label1.htmlFor = letter.id;
    const label2 = element("label", "Resume text (optional if already on file)", "form-label");
    label2.htmlFor = resume.id;
    const submit = element("button", "Submit application", "board-button");
    submit.type = "submit";
    form.append(label1, letter, label2, resume, submit);
    form.addEventListener("submit", async event => {
      event.preventDefault();
      submit.disabled = true;
      await run(async () => {
        await api("/graduates/applications", "POST", {
          listing_id: job.id,
          cover_letter: letter.value,
          resume_text: resume.value || null
        });
        form.reset();
        form.hidden = true;
        await loadApplications();
        message("Application submitted.");
      });
      submit.disabled = false;
    });
    return form;
  }

  function graduateJob(job) {
    const item = jobCard(job);
    if (role !== "graduate") return item;
    if (job.apply_mode === "external") {
      const url = safeLink(job.external_url);
      if (url) {
        const link = element("a", "Apply on company website", "board-button");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        item.append(link);
      } else {
        item.append(element("p", "External application link unavailable.", "card-meta"));
      }
    } else if (job.apply_mode === "collect") {
      const form = applyForm(job);
      form.hidden = true;
      item.append(button("Apply for this job", () => {
        form.hidden = !form.hidden;
        if (!form.hidden) form.querySelector("textarea").focus();
      }), form);
    }
    return item;
  }

  function renderJobs() {
    const search = byId("job-search")?.value.toLowerCase() || "";
    const matches = jobs.filter(job =>
      [job.title, job.company, job.description].join(" ").toLowerCase().includes(search)
    );
    showList("job-list", matches, graduateJob, "No matching jobs found.");
  }

  async function loadJobs() {
    jobs = (await api("/jobs")).jobs;
    renderJobs();
  }

  function historyPanel(applicationId) {
    const panel = element("div", null, "history-panel");
    panel.hidden = true;
    const trigger = button("View history", async () => {
      if (!panel.hidden) {
        panel.hidden = true;
        trigger.textContent = "View history";
        return;
      }
      const result = await api("/applications/" + applicationId + "/history");
      panel.replaceChildren(element("h4", "Status history"));
      if (!result.history.length) panel.append(element("p", "No status changes yet."));
      result.history.forEach(entry => {
        const line = element("p", entry.previous_status + " → " + entry.new_status, "history-entry");
        const date = new Date(entry.timestamp);
        const timestamp = Number.isNaN(date.getTime()) ? entry.timestamp : date.toLocaleString();
        line.append(element("small", "Changed by user #" + entry.actor_id + " · " + timestamp));
        panel.append(line);
      });
      panel.hidden = false;
      trigger.textContent = "Hide history";
    }, "secondary");
    return [trigger, panel];
  }

  async function loadApplications() {
    const result = await api("/graduates/applications");
    showList("application-list", result.applications, app => {
      const job = jobs.find(item => item.id === app.listing_id);
      const item = card(job ? job.title : "Listing #" + app.listing_id, "Application #" + app.id, app.status);
      item.append(...historyPanel(app.id));
      return item;
    }, "You have not submitted any applications yet.");
  }

  async function loadNotifications() {
    const result = await api("/graduates/notifications");
    showList("notification-list", [...result.notifications].reverse(), note => {
      const item = element("article", null, "board-card notification");
      item.append(element("span", "Update", "notification-label"), element("p", note.message));
      return item;
    }, "No notifications yet.");
  }

  async function startGraduate() {
    byId("job-search").addEventListener("input", renderJobs);
    byId("subscribe").addEventListener("click", () => run(async () => {
      await api("/graduates/subscribe", "POST");
      message("You are subscribed to job alerts.");
    }));
    byId("refresh-notifications").addEventListener("click", () => run(loadNotifications));
    await loadJobs();
    await loadApplications();
    await loadNotifications();
  }

  function resetListingForm() {
    editId = null;
    byId("listing-form").reset();
    byId("listing-heading").textContent = "Create a job listing";
    byId("listing-submit").textContent = "Submit for approval";
    byId("cancel-edit").hidden = true;
    toggleExternal();
  }

  function toggleExternal() {
    const external = byId("apply-mode").value === "external";
    byId("external-field").hidden = !external;
    byId("external-url").required = external;
    byId("external-url").disabled = !external;
  }

  function editListing(job) {
    editId = job.id;
    const form = byId("listing-form");
    ["title", "company", "description", "apply_mode", "deadline", "external_url"].forEach(name => {
      form.elements.namedItem(name).value = job[name] || "";
    });
    byId("listing-heading").textContent = "Edit rejected listing";
    byId("listing-submit").textContent = "Save changes";
    byId("cancel-edit").hidden = false;
    toggleExternal();
    byId("new-listing").scrollIntoView({ behavior: "smooth" });
    byId("job-title").focus();
  }

  async function loadListings() {
    const result = await api("/employer/listings");
    showList("listing-list", result.listings, job => {
      const item = jobCard(job);
      const actions = row();
      actions.append(button("View applicants", () => loadApplicants(job), "secondary"));
      if (job.status === "rejected") {
        actions.append(button("Edit listing", () => editListing(job), "secondary"));
        actions.append(button("Resubmit", async () => {
          await api("/employer/listings/" + job.id + "/resubmit", "POST");
          await loadListings();
          message("Listing resubmitted for approval.");
        }));
      }
      item.append(actions);
      return item;
    }, "No listings yet. Create a job listing above.");
  }

  async function loadApplicants(job) {
    const result = await api("/listings/" + job.id + "/applicants");
    byId("applicant-heading").textContent = "Applications for " + job.title;
    showList("applicant-list", result.applicants, app => {
      const item = card("Application #" + app.id, "Graduate #" + app.graduate_id, app.status);
      const details = element("details", null, "applicant-details");
      details.append(element("summary", "Cover letter and resume"), element("h4", "Cover letter"),
        element("p", app.cover_letter), element("h4", "Resume"), element("p", app.resume_text));
      const actions = row();
      // the backend still validates each transition
      const allowed = {
        submitted: [["Mark reviewed", "mark_reviewed"]],
        reviewed: [["Shortlist", "shortlist"], ["Reject", "reject"]],
        shortlisted: [["Hire", "hire"], ["Reject", "reject"]]
      };
      (allowed[app.status] || []).forEach(([label, action]) => {
        actions.append(button(label, async () => {
          await api("/applications/" + app.id + "/transition", "POST", { action });
          await loadApplicants(job);
          message("Application status updated.");
        }, action === "reject" ? "danger" : ""));
      });
      item.append(details, actions, ...historyPanel(app.id));
      return item;
    }, "No applications for this listing yet.");
    byId("applicants").scrollIntoView({ behavior: "smooth" });
  }

  async function startEmployer() {
    const form = byId("listing-form");
    byId("apply-mode").addEventListener("change", toggleExternal);
    byId("cancel-edit").addEventListener("click", resetListingForm);
    toggleExternal();
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = byId("listing-submit");
      submit.disabled = true;
      await run(async () => {
        const data = Object.fromEntries(new FormData(form));
        if (data.apply_mode !== "external") data.external_url = null;
        const editing = editId !== null;
        await api(editing ? "/employer/listings/" + editId : "/employer/listings",
          editing ? "PUT" : "POST", data);
        resetListingForm();
        await loadListings();
        message(editing ? "Listing updated. Resubmit when ready." : "Listing submitted for approval.");
      });
      submit.disabled = false;
    });
    await loadListings();
  }

  async function loadAdmin() {
    const pending = (await api("/admin/listings/pending")).listings;
    showList("pending-list", pending, job => {
      const item = jobCard(job);
      const actions = row();
      for (const [label, action] of [["Approve & publish", "publish"], ["Reject", "reject"]]) {
        actions.append(button(label, async () => {
          await api("/admin/listings/" + job.id + "/" + action, "POST");
          await loadAdmin();
          message(action === "publish" ? "Listing published." : "Listing rejected.");
        }, action === "reject" ? "danger" : ""));
      }
      item.append(actions);
      return item;
    }, "No listings are waiting for approval.");
    const published = (await api("/jobs")).jobs;
    showList("published-list", published, job => {
      const item = jobCard(job);
      item.append(button("Export applicants", async () => {
        const result = await api("/admin/listings/" + job.id + "/export");
        const blob = new Blob([JSON.stringify(result.package, null, 2)], { type: "application/json" });
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.href = url;
        link.download = "applicants-" + job.id + ".json";
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        message("Applicant package downloaded.");
      }, "secondary"));
      return item;
    }, "No active published jobs.");
  }

  if (role === "graduate") run(startGraduate);
  else if (role === "employer") run(startEmployer);
  else if (role === "admin") {
    byId("refresh-admin").addEventListener("click", () => run(loadAdmin));
    run(loadAdmin);
  } else run(loadJobs);
}
