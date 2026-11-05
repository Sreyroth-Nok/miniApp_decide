import { api } from './api.js';
import * as tg from './tg.js';
import { h, listNames, optStyle, plural, toast } from './ui.js';
import { Wheel } from './wheel.js';

const root = document.getElementById('app');
const LIVE_REFRESH_MS = 3000;

const state = {
  stack: [],          // screens, newest last
  poll: null,         // poll on the current screen
  config: { dev_mode: false, app_link: '' },
  cleanup: null,      // undoes the current screen's listeners
  draft: newDraft(),  // the create form
};

function newDraft() {
  return {
    question: '',
    options: ['', ''],
    mode: 'single',
    allow_add: false,
    anonymous: false,
    close_after_minutes: 0,
  };
}

const MODES = [
  { id: 'single', name: 'Pick one', text: 'Everyone chooses a single option.' },
  { id: 'ranked', name: 'Rank them', text: 'Everyone puts the options in order. The least popular drop out until one has a majority.' },
  { id: 'swipe', name: 'Swipe cards', text: 'One card per option. Swipe right for yes, left for no.' },
  { id: 'spin', name: 'Just spin', text: 'No voting. Add the options and let the wheel choose.' },
];

const TEMPLATES = [
  { name: 'Lunch', question: 'Where should we eat lunch?', options: ['Noodles', 'Rice', 'Pizza', 'Burgers'], mode: 'single' },
  { name: 'Movie night', question: 'What should we watch?', options: ['Comedy', 'Action', 'Horror', 'Animation'], mode: 'ranked' },
  { name: 'Weekend plan', question: 'What are we doing this weekend?', options: ['Cafe', 'Karaoke', 'Beach trip', 'Stay in and game'], mode: 'swipe' },
  { name: 'Who pays', question: 'Who pays this time?', options: ['', '', ''], mode: 'spin' },
];

/* ---------- navigation ---------- */

function go(screen) {
  state.stack.push(screen);
  render();
}

function replace(screen) {
  state.stack[state.stack.length - 1] = screen;
  render();
}

function back() {
  if (state.stack.length > 1) state.stack.pop();
  render();
}

function backControl() {
  if (state.stack.length < 2 || tg.hasNativeBack()) return null;
  return h('button', { class: 'text-btn back', type: 'button', onclick: back }, 'Back');
}

const SCREENS = { home: homeScreen, vote: voteScreen, results: resultsScreen, spin: spinScreen, share: shareScreen };

async function render() {
  state.cleanup?.();
  state.cleanup = null;
  tg.hideMain();
  tg.setBack(state.stack.length > 1 ? back : null);
  const screen = state.stack[state.stack.length - 1];
  try {
    await SCREENS[screen.name](screen);
  } catch (err) {
    errorScreen(err);
  }
  window.scrollTo(0, 0);
}

function show(...nodes) {
  root.replaceChildren(...nodes.flat(Infinity).filter(Boolean));
}

function errorScreen(err) {
  tg.hideMain();
  show(h('div', { class: 'center' },
    h('h1', {}, 'That didn\'t open'),
    h('p', { class: 'hint' }, err.message),
    h('button', {
      class: 'btn primary',
      type: 'button',
      onclick: () => { state.stack = [{ name: 'home' }]; render(); },
    }, 'Start a new decision')));
}

async function act(task) {
  tg.setMainBusy(true);
  try {
    return await task();
  } catch (err) {
    tg.haptic.warn();
    toast(err.message);
    return null;
  } finally {
    tg.setMainBusy(false);
  }
}

// Keeps a screen up to date while other people vote or spin.
function liveRefresh(id, onChange) {
  const strip = (poll) => JSON.stringify(poll, (key, value) => (key === 'age' ? undefined : value));
  let seen = strip(state.poll);
  const tick = async () => {
    if (document.hidden) return;
    try {
      const fresh = await api.poll(id);
      const next = strip(fresh);
      if (next !== seen) {
        seen = next;
        state.poll = fresh;
        onChange(fresh);
      }
    } catch { /* a missed refresh is harmless; the next one retries */ }
  };
  const timer = setInterval(tick, LIVE_REFRESH_MS);
  return () => clearInterval(timer);
}

const optionIndex = (poll, id) => poll.options.findIndex((o) => o.id === id);
const optionById = (poll, id) => poll.options.find((o) => o.id === id);

/* ---------- home: create a decision ---------- */

async function homeScreen() {
  const { draft } = state;
  const error = h('p', { class: 'error', role: 'alert', hidden: true });

  const questionInput = h('textarea', {
    class: 'field question',
    rows: 2,
    maxLength: 140,
    placeholder: 'Where should we eat lunch?',
    'aria-label': 'Your question',
    value: draft.question,
    oninput: (e) => { draft.question = e.target.value; },
  });

  const optionsBox = h('div', {});
  const renderOptions = () => {
    optionsBox.replaceChildren(...draft.options.map((value, i) => h('div', { class: 'opt-row', style: optStyle(i) },
      h('span', { class: 'dot', 'aria-hidden': 'true' }),
      h('input', {
        class: 'opt-input',
        maxLength: 40,
        placeholder: `Option ${i + 1}`,
        'aria-label': `Option ${i + 1}`,
        value,
        oninput: (e) => { draft.options[i] = e.target.value; },
        onkeydown: (e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          addRow();
        },
      }),
      draft.options.length > 2 && h('button', {
        class: 'icon-btn',
        type: 'button',
        'aria-label': `Remove option ${i + 1}`,
        onclick: () => { draft.options.splice(i, 1); renderOptions(); },
      }, '×'))));
    addButton.hidden = draft.options.length >= 12;
  };
  const addRow = () => {
    if (draft.options.length >= 12) return;
    draft.options.push('');
    renderOptions();
    optionsBox.querySelector('.opt-row:last-child input').focus();
  };
  const addButton = h('button', { class: 'text-btn', type: 'button', onclick: addRow }, 'Add an option');
  renderOptions();

  const toggle = (key, label) => h('label', { class: 'toggle' }, label, h('input', {
    type: 'checkbox',
    checked: draft[key],
    onchange: (e) => { draft[key] = e.target.checked; },
  }));

  const applyMainLabel = () => tg.setMain(draft.mode === 'spin' ? 'Create wheel' : 'Create poll', submit);

  const submit = async () => {
    error.hidden = true;
    const options = draft.options.map((o) => o.trim()).filter(Boolean);
    const problem = !draft.question.trim() ? 'Write the question first.'
      : options.length < 2 ? 'Add at least two options.' : '';
    if (problem) {
      error.textContent = problem;
      error.hidden = false;
      tg.haptic.warn();
      return;
    }
    const poll = await act(() => api.create({ ...draft, options }));
    if (!poll) return;
    tg.haptic.win();
    state.draft = newDraft();
    state.poll = poll;
    state.stack = [{ name: 'home' }, { name: 'share', id: poll.id, fresh: true }];
    render();
  };

  const recent = await api.recent().catch(() => ({ mine: [], chat: [] }));
  const decisionList = (items) => h('div', { class: 'list' }, items.map((item) => h('button', {
    class: 'list-item',
    type: 'button',
    onclick: () => go({ name: item.mode === 'spin' ? 'spin' : 'results', id: item.id }),
  },
    h('span', { class: 'q' }, item.question),
    h('span', { class: 'state' }, item.closed ? 'Closed' : item.mode === 'spin' ? 'Wheel' : 'Open'))));

  show(
    state.config.dev_mode && !tg.inTelegram && h('p', { class: 'dev-note' }, `Browser test mode, signed in as ${tg.devUser()}.`),
    recent.chat.length > 0 && [h('h2', { style: 'margin-top:0' }, 'Decisions in this chat'), decisionList(recent.chat.slice(0, 3))],
    h('h1', { style: recent.chat.length ? 'margin-top:28px' : '' }, 'What are we deciding?'),
    questionInput,
    h('div', { class: 'chips' }, TEMPLATES.map((t) => h('button', {
      class: 'chip',
      type: 'button',
      onclick: () => {
        Object.assign(draft, { question: t.question, options: [...t.options], mode: t.mode });
        render();
      },
    }, t.name))),
    h('h2', {}, 'Options'),
    optionsBox,
    addButton,
    h('h2', {}, 'How should the group decide?'),
    h('div', { class: 'modes' }, MODES.map((m) => h('label', { class: 'mode' },
      h('input', {
        type: 'radio',
        name: 'mode',
        value: m.id,
        checked: draft.mode === m.id,
        onchange: () => { draft.mode = m.id; applyMainLabel(); },
      }),
      h('strong', {}, m.name),
      h('span', {}, m.text)))),
    h('details', {},
      h('summary', {}, 'More settings'),
      toggle('allow_add', 'Let anyone add options'),
      toggle('anonymous', 'Hide who voted'),
      h('label', { class: 'toggle' }, 'Close automatically', h('select', {
        class: 'field',
        style: 'width:auto',
        onchange: (e) => { draft.close_after_minutes = Number(e.target.value); },
      },
        [[0, 'Never'], [60, 'After 1 hour'], [1440, 'After 1 day']].map(([value, label]) => h('option', {
          value,
          selected: draft.close_after_minutes === value,
        }, label))))),
    error,
    recent.mine.length > 0 && [h('h2', {}, 'Your decisions'), decisionList(recent.mine)],
  );
  applyMainLabel();
}

/* ---------- vote ---------- */

async function voteScreen({ id }) {
  const poll = await api.poll(id);
  state.poll = poll;
  if (poll.mode === 'spin') { replace({ name: 'spin', id }); return; }
  if (poll.closed) { replace({ name: 'results', id }); return; }

  const heading = [
    backControl(),
    h('h1', {}, poll.question),
    h('p', { class: 'hint', id: 'voter-count' }, `${poll.owner_name}'s poll. ${plural(poll.voter_count, 'vote')} so far.`),
  ];
  const submit = async (choices) => {
    const updated = await act(() => api.vote(id, choices));
    if (!updated) return;
    tg.haptic.win();
    state.poll = updated;
    replace({ name: 'results', id });
  };

  let stopSwipeKeys = null;
  if (poll.mode === 'single') voteSingle(poll, heading, submit);
  else if (poll.mode === 'ranked') voteRanked(poll, heading, submit);
  else stopSwipeKeys = voteSwipe(poll, heading, submit);
  const stopRefresh = liveRefresh(id, (fresh) => {
    const count = document.getElementById('voter-count');
    if (count) count.textContent = `${fresh.owner_name}'s poll. ${plural(fresh.voter_count, 'vote')} so far.`;
  });
  state.cleanup = () => { stopRefresh(); stopSwipeKeys?.(); };
}

function addOptionForm(poll, onDone) {
  if (poll.closed || !(poll.allow_add || poll.is_owner) || poll.options.length >= 12) return null;
  const input = h('input', {
    class: 'field grow',
    maxLength: 40,
    placeholder: 'Suggest another option',
    'aria-label': 'Suggest another option',
  });
  const add = async () => {
    const label = input.value.trim();
    if (!label) return;
    const updated = await act(() => api.addOption(poll.id, label));
    if (updated) { state.poll = updated; onDone(updated); }
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
  return h('div', { class: 'row', style: 'margin-top:16px' }, input, h('button', { class: 'btn', type: 'button', onclick: add }, 'Add'));
}

function voteSingle(poll, heading, submit) {
  let chosen = poll.my_ballot?.[0] ?? null;
  const list = h('div', { class: 'choices' });
  const update = () => {
    const current = state.poll;
    list.replaceChildren(...current.options.map((option, i) => h('button', {
      class: 'choice',
      type: 'button',
      style: optStyle(i),
      'aria-pressed': String(chosen === option.id),
      onclick: () => { chosen = option.id; tg.haptic.tick(); update(); },
    },
      h('span', { class: 'rank-badge empty', 'aria-hidden': 'true' }),
      h('span', { class: 'label' }, option.label))));
    tg.setMain(poll.my_ballot ? 'Update my vote' : 'Submit vote', () => submit([chosen]), { active: chosen !== null });
  };
  show(heading, list, addOptionForm(poll, update));
  update();
}

function voteRanked(poll, heading, submit) {
  const order = (poll.my_ballot ?? []).slice();
  const list = h('div', { class: 'choices' });
  const update = () => {
    const current = state.poll;
    const ranked = order.map((id) => optionById(current, id)).filter(Boolean);
    const rest = current.options.filter((o) => !order.includes(o.id));
    const row = (option) => {
      const position = order.indexOf(option.id);
      const inOrder = position >= 0;
      return h('button', {
        class: `choice${inOrder ? ' ranked' : ''}`,
        type: 'button',
        style: optStyle(optionIndex(current, option.id)),
        'aria-label': inOrder ? `${option.label}, ranked ${position + 1}. Remove from ranking` : `Add ${option.label} to ranking`,
        onclick: () => {
          if (inOrder) order.splice(position, 1); else order.push(option.id);
          tg.haptic.tick();
          update();
        },
      },
        h('span', { class: `rank-badge${inOrder ? '' : ' empty'}`, 'aria-hidden': 'true' }, inOrder ? String(position + 1) : ''),
        h('span', { class: 'label' }, option.label));
    };
    list.replaceChildren(...ranked.map(row), ...rest.map(row));
    tg.setMain(poll.my_ballot ? 'Update my ranking' : 'Submit ranking', () => submit(order), { active: order.length > 0 });
  };
  show(
    heading,
    h('p', {}, 'Tap your favourite first, then your next choice. Tap again to undo. You can leave out anything you\'d never pick.'),
    list,
    addOptionForm(poll, update),
  );
  update();
}

function voteSwipe(poll, heading, submit) {
  let position = 0;
  const yes = [];
  const history = [];
  const deck = h('div', { class: 'deck' });
  const actions = h('div', {});
  const progress = h('p', { class: 'hint' });

  const answer = (liked, card) => {
    const option = poll.options[position];
    const finish = () => {
      history.push(liked);
      if (liked) yes.push(option.id);
      position += 1;
      update();
    };
    tg.haptic.tap();
    if (!card) { finish(); return; }
    card.classList.add('leaving');
    card.style.transform = `translateX(${liked ? 130 : -130}%) rotate(${liked ? 14 : -14}deg)`;
    setTimeout(finish, 210);
  };

  const undo = () => {
    position -= 1;
    if (history.pop()) yes.pop();
    update();
  };

  const attachDrag = (card) => {
    const stampYes = card.querySelector('.stamp.yes');
    const stampNo = card.querySelector('.stamp.no');
    let startX = null;
    let dx = 0;
    card.addEventListener('pointerdown', (e) => {
      startX = e.clientX;
      card.setPointerCapture(e.pointerId);
      card.classList.remove('back-home');
    });
    card.addEventListener('pointermove', (e) => {
      if (startX === null) return;
      dx = e.clientX - startX;
      card.style.transform = `translateX(${dx}px) rotate(${dx / 16}deg)`;
      stampYes.style.opacity = Math.max(0, dx / 90);
      stampNo.style.opacity = Math.max(0, -dx / 90);
    });
    const release = () => {
      if (startX === null) return;
      startX = null;
      if (Math.abs(dx) > 90) { answer(dx > 0, card); return; }
      dx = 0;
      card.classList.add('back-home');
      card.style.transform = '';
      stampYes.style.opacity = 0;
      stampNo.style.opacity = 0;
    };
    card.addEventListener('pointerup', release);
    card.addEventListener('pointercancel', release);
  };

  const makeCard = (option, index, isTop) => {
    const card = h('div', { class: `card ${isTop ? 'top' : 'next'}`, style: optStyle(index), 'aria-hidden': isTop ? null : 'true' },
      h('span', { class: 'stamp yes', 'aria-hidden': 'true' }, 'Yes'),
      h('span', { class: 'stamp no', 'aria-hidden': 'true' }, 'No'),
      h('span', {}, option.label));
    if (isTop) attachDrag(card);
    return card;
  };

  const update = () => {
    const { options } = poll;
    if (position >= options.length) {
      deck.replaceChildren(h('div', { class: 'verdict', style: 'margin:0' },
        h('div', { class: 'big' }, `Yes to ${yes.length} of ${options.length}`),
        h('div', { class: 'small' }, yes.length
          ? listNames(yes.map((id) => optionById(poll, id).label))
          : 'You said no to everything. Your vote still counts.')));
      deck.style.height = 'auto';
      deck.style.minHeight = '0';
      actions.replaceChildren(h('button', { class: 'text-btn', type: 'button', onclick: undo }, 'Go back a card'));
      progress.textContent = '';
      tg.setMain(poll.my_ballot ? 'Update my votes' : 'Submit votes', () => submit(yes));
      return;
    }
    deck.style.height = '';
    deck.style.minHeight = '';
    tg.hideMain();
    const cards = [];
    if (options[position + 1]) cards.push(makeCard(options[position + 1], position + 1, false));
    const top = makeCard(options[position], position, true);
    cards.push(top);
    deck.replaceChildren(...cards);
    progress.textContent = `Card ${position + 1} of ${options.length}`;
    actions.replaceChildren(h('div', { class: 'swipe-actions' },
      h('button', { class: 'btn', type: 'button', onclick: () => answer(false, top) }, 'No'),
      h('button', { class: 'btn primary', type: 'button', onclick: () => answer(true, top) }, 'Yes')));
    if (position > 0) {
      actions.append(h('button', { class: 'text-btn', type: 'button', onclick: undo }, 'Go back a card'));
    }
  };

  show(heading, progress, deck, actions);
  update();

  const keys = (e) => {
    if (position >= poll.options.length) return;
    const top = deck.querySelector('.card.top');
    if (e.key === 'ArrowRight') answer(true, top);
    if (e.key === 'ArrowLeft') answer(false, top);
  };
  document.addEventListener('keydown', keys);
  return () => document.removeEventListener('keydown', keys);
}

/* ---------- results ---------- */

function bars(poll, rows, eliminated = []) {
  const top = Math.max(1, ...rows.map((r) => r.count));
  return h('div', { class: 'bars' }, rows.map((row) => h('div', {
    class: `bar-row${eliminated.includes(row.id) ? ' out' : ''}`,
    style: optStyle(optionIndex(poll, row.id)),
  },
    h('div', { class: 'bar-head' },
      h('span', {}, row.label),
      h('span', { class: 'n', 'aria-label': plural(row.count, 'vote') }, String(row.count))),
    h('div', { class: 'bar-track', 'aria-hidden': 'true' },
      h('div', { class: 'bar-fill', style: `width:${(row.count / top) * 100}%` })))));
}

function verdict(poll) {
  const { decision, results, closed } = poll;
  if (decision) {
    const how = decision.source === 'spin' ? 'Picked by the wheel' : 'Picked by the group';
    return h('section', { class: 'verdict won', style: optStyle(optionIndex(poll, decision.id)) },
      h('div', { class: 'big' }, decision.label),
      h('div', { class: 'small' }, how));
  }
  if (!results) {
    return h('section', { class: 'verdict' },
      h('div', { class: 'big' }, 'Vote to see the results'),
      h('div', { class: 'small' }, `${plural(poll.voter_count, 'vote')} so far`));
  }
  if (results.tied) {
    const names = results.winners.map((id) => optionById(poll, id).label);
    return h('section', { class: 'verdict' },
      h('div', { class: 'big' }, closed ? 'It ended in a tie' : 'It\'s a tie so far'),
      h('div', { class: 'small' }, listNames(names)),
      h('button', {
        class: 'btn primary block',
        type: 'button',
        onclick: () => go({ name: 'spin', id: poll.id, scope: 'tied' }),
      }, `Spin between these ${names.length}`));
  }
  if (results.winners.length === 1) {
    const leader = optionById(poll, results.winners[0]);
    return h('section', { class: 'verdict won', style: optStyle(optionIndex(poll, leader.id)) },
      h('div', { class: 'big' }, leader.label),
      h('div', { class: 'small' }, closed ? 'Picked by the group' : `In the lead, with ${plural(poll.voter_count, 'vote')} in`));
  }
  return h('section', { class: 'verdict' },
    h('div', { class: 'big' }, closed ? 'Nobody voted' : 'No votes yet'),
    h('div', { class: 'small' }, 'Share it with the group to get started.'));
}

function roundsView(poll, screen) {
  const { rounds } = poll.results;
  const eliminatedSoFar = (upto) => rounds.slice(0, upto).flatMap((r) => r.eliminated.map((o) => o.id));
  const index = Math.min(screen.round ?? rounds.length - 1, rounds.length - 1);
  const round = rounds[index];
  const previouslyOut = eliminatedSoFar(index);
  const rows = [...round.counts].sort((a, b) => b.count - a.count);
  const notes = [];
  if (round.eliminated.length) {
    const names = listNames(round.eliminated.map((o) => o.label));
    notes.push(`${names} had the fewest votes and ${round.eliminated.length > 1 ? 'drop' : 'drops'} out. Those ballots move to each voter's next choice.`);
  }
  if (round.tiebreak) notes.push('Last place was tied, so overall rankings decided who went out.');
  if (round.exhausted) notes.push(`${plural(round.exhausted, 'ballot')} had no choices left.`);
  if (previouslyOut.length === 0 && index === rounds.length - 1 && !round.eliminated.length) {
    notes.push('Decided in the first count.');
  }
  const step = (delta) => { screen.round = index + delta; render(); };
  return [
    h('h2', {}, 'How the count went'),
    rounds.length > 1 && h('div', { class: 'round-nav' },
      h('button', { class: 'btn', type: 'button', disabled: index === 0, onclick: () => step(-1) }, 'Earlier'),
      h('strong', { 'aria-live': 'polite' }, `Round ${index + 1} of ${rounds.length}`),
      h('button', { class: 'btn', type: 'button', disabled: index === rounds.length - 1, onclick: () => step(1) }, 'Later')),
    bars(poll, rows, round.eliminated.map((o) => o.id)),
    notes.length > 0 && h('p', { class: 'round-note' }, notes.join(' ')),
  ];
}

function resultsBody(poll, screen) {
  const voted = poll.my_ballot !== null;
  const { results } = poll;
  const actions = [];

  if (voted && !poll.closed) {
    actions.push(h('button', { class: 'btn block', type: 'button', onclick: () => go({ name: 'vote', id: poll.id }) }, 'Change my vote'));
  }
  if (results && !poll.decision) {
    actions.push(h('button', { class: 'btn block', type: 'button', onclick: () => go({ name: 'spin', id: poll.id }) }, 'Open the wheel'));
  }
  if (poll.is_owner) {
    if (results?.winners.length === 1 && !poll.decision) {
      const leader = optionById(poll, results.winners[0]);
      actions.push(h('button', {
        class: 'btn block',
        type: 'button',
        onclick: async () => {
          const updated = await act(() => api.decide(poll.id, leader.id));
          if (updated) { tg.haptic.win(); state.poll = updated; render(); }
        },
      }, `Make ${leader.label} final`));
    }
    if (!poll.closed) {
      actions.push(h('button', {
        class: 'btn block danger',
        type: 'button',
        onclick: async () => {
          const updated = await act(() => api.close(poll.id));
          if (updated) { state.poll = updated; render(); }
        },
      }, 'Close voting'));
    } else {
      actions.push(h('button', {
        class: 'btn block',
        type: 'button',
        onclick: async () => {
          const updated = await act(() => api.reopen(poll.id));
          if (updated) { state.poll = updated; render(); }
        },
      }, 'Reopen'));
    }
  }

  return [
    backControl(),
    h('h1', {}, poll.question),
    verdict(poll),
    results && (results.rounds
      ? roundsView(poll, screen)
      : bars(poll, results.tally)),
    !poll.anonymous && poll.voters.length > 0 && h('p', { class: 'hint', style: 'margin-top:16px' }, `Voted: ${listNames(poll.voters)}`),
    poll.anonymous && poll.voter_count > 0 && h('p', { class: 'hint', style: 'margin-top:16px' }, `${plural(poll.voter_count, 'vote')} in. Names are hidden.`),
    voted && addOptionForm(poll, () => render()),
    h('div', { class: 'stack' }, actions.filter(Boolean)),
  ];
}

async function resultsScreen(screen) {
  const { id } = screen;
  if (state.poll?.id !== id) state.poll = await api.poll(id);
  state.poll = await api.poll(id);
  const poll = state.poll;
  if (poll.mode === 'spin') { replace({ name: 'spin', id }); return; }

  const paint = (current) => {
    show(resultsBody(current, screen));
    if (current.my_ballot === null && !current.closed) {
      tg.setMain('Vote now', () => go({ name: 'vote', id }));
    } else {
      tg.setMain(current.decision ? 'Share the result' : 'Share with the group', () => go({ name: 'share', id }));
    }
  };
  paint(poll);
  state.cleanup = liveRefresh(id, (fresh) => {
    if (document.activeElement?.tagName !== 'INPUT') paint(fresh);
  });
}

/* ---------- spin ---------- */

async function spinScreen(screen) {
  const { id } = screen;
  let poll = await api.poll(id);
  state.poll = poll;
  const isWheelOnly = poll.mode === 'spin';
  const mustVote = !isWheelOnly && !poll.results;

  const settings = {
    scope: screen.scope === 'tied' && poll.results?.tied ? 'tied' : 'all',
    weighted: false,
    eliminate: false,
    excluded: [],
  };
  let spinning = false;
  let shownSpin = null;
  let landed = null; // { id, by } for the spin on show

  const canvas = h('canvas', { role: 'img', 'aria-label': 'Spin wheel' });
  const pointer = h('div', { class: 'pointer', 'aria-hidden': 'true' });
  const hub = h('button', { class: 'hub', type: 'button', 'aria-label': 'Spin the wheel', onclick: () => doSpin() }, 'Spin');
  const status = h('div', { class: 'spin-status', 'aria-live': 'polite' });
  const controls = h('div', {});

  const wheel = new Wheel(canvas, {
    colorIndex: (optionId) => optionIndex(state.poll, optionId),
    onTick: () => {
      tg.haptic.tick();
      pointer.classList.remove('kick');
      void pointer.offsetWidth; // restarts the CSS animation
      pointer.classList.add('kick');
    },
  });

  const previewSlices = () => {
    let list = poll.options.filter((o) => !settings.excluded.includes(o.id));
    if (settings.scope === 'tied' && poll.results?.tied) {
      list = list.filter((o) => poll.results.winners.includes(o.id));
    }
    return list
      .map((o) => ({
        id: o.id,
        label: o.label,
        weight: settings.weighted ? (poll.results?.spin_weights[o.id] ?? 0) : 1,
      }))
      .filter((s) => s.weight > 0);
  };

  const resetWheel = () => {
    landed = null;
    shownSpin = null;
    wheel.setSlices(previewSlices());
    paint();
  };

  const decidedAlready = () => Boolean(poll.decision);
  const remaining = () => previewSlices();

  const paintMain = () => {
    if (mustVote && !poll.results) {
      tg.setMain('Vote first', () => replace({ name: 'vote', id }));
    } else if (decidedAlready()) {
      tg.setMain('Share the result', () => go({ name: 'share', id }));
    } else {
      tg.setMain(landed ? 'Spin again' : 'Spin the wheel', doSpin, { active: !spinning && remaining().length >= 2 });
    }
    hub.disabled = spinning || decidedAlready() || (mustVote && !poll.results) || remaining().length < 2;
  };

  const paintStatus = () => {
    if (poll.decision) {
      status.replaceChildren(
        h('div', { class: 'big' }, poll.decision.label),
        h('div', { class: 'small' }, poll.decision.source === 'spin' ? 'Final. Picked by the wheel.' : 'Final. Picked by the group.'),
      );
    } else if (spinning) {
      status.replaceChildren(h('div', { class: 'small' }, 'Spinning…'));
    } else if (landed) {
      const label = optionById(poll, landed.id)?.label ?? '';
      status.replaceChildren(
        h('div', { class: 'big' }, label),
        h('div', { class: 'small' }, `Spun by ${landed.by}`),
      );
    } else if (mustVote && !poll.results) {
      status.replaceChildren(h('div', { class: 'small' }, 'Vote first, then you can use the wheel.'));
    } else if (remaining().length === 1) {
      status.replaceChildren(
        h('div', { class: 'big' }, remaining()[0].label),
        h('div', { class: 'small' }, 'Last one left'),
      );
    } else if (remaining().length === 0) {
      status.replaceChildren(h('div', { class: 'small' }, 'There are no votes to put on the wheel yet.'));
    } else {
      status.replaceChildren(h('div', { class: 'small' }, `${plural(remaining().length, 'option')} on the wheel`));
    }
  };

  const paintControls = () => {
    const parts = [];
    const open = !decidedAlready() && !(mustVote && !poll.results);
    const lastAlive = remaining().length === 1 ? remaining()[0] : null;
    const finalCandidate = landed?.id ?? lastAlive?.id ?? null;

    if (poll.is_owner && !decidedAlready() && finalCandidate && !spinning) {
      const label = optionById(poll, finalCandidate)?.label;
      parts.push(h('button', {
        class: 'btn primary block',
        type: 'button',
        onclick: async () => {
          const updated = await act(() => api.decide(id, finalCandidate));
          if (updated) { tg.haptic.win(); poll = updated; state.poll = updated; paint(); }
        },
      }, `Make ${label} final`));
    }

    if (open && !spinning) {
      if (!isWheelOnly && poll.results) {
        const segment = (label, active, onclick) => h('button', { type: 'button', 'aria-pressed': String(active), onclick }, label);
        const buttons = [
          segment('Equal chance', settings.scope === 'all' && !settings.weighted, () => {
            Object.assign(settings, { scope: 'all', weighted: false }); resetWheel();
          }),
          segment('By votes', settings.scope === 'all' && settings.weighted, () => {
            Object.assign(settings, { scope: 'all', weighted: true }); resetWheel();
          }),
          poll.results.tied && segment('Tied only', settings.scope === 'tied', () => {
            Object.assign(settings, { scope: 'tied', weighted: false }); resetWheel();
          }),
        ].filter(Boolean);
        parts.push(h('div', { class: 'segmented', style: 'margin-top:12px' }, buttons));
      }
      parts.push(h('label', { class: 'toggle' }, 'Remove each result and spin again', h('input', {
        type: 'checkbox',
        checked: settings.eliminate,
        onchange: (e) => {
          settings.eliminate = e.target.checked;
          settings.excluded = [];
          resetWheel();
        },
      })));
    }

    if (settings.excluded.length) {
      parts.push(h('div', { class: 'out-list', 'aria-label': 'Removed from the wheel' }, settings.excluded.map((optionId) => h('span', { class: 'out-tag' }, optionById(poll, optionId)?.label))));
    }
    if (shownSpin && !spinning) {
      parts.push(h('button', {
        class: 'text-btn',
        type: 'button',
        onclick: () => playSpin(shownSpin),
      }, 'Replay this spin'));
    }
    if (!isWheelOnly) {
      parts.push(h('button', { class: 'text-btn', type: 'button', style: 'display:block', onclick: () => go({ name: 'results', id }) }, 'See the votes'));
    } else if (!decidedAlready()) {
      parts.push(h('button', { class: 'text-btn', type: 'button', style: 'display:block', onclick: () => go({ name: 'share', id }) }, 'Send this wheel to the group'));
      const form = addOptionForm(poll, (updated) => { poll = updated; if (!shownSpin) resetWheel(); else paint(); });
      if (form) parts.push(form);
    }
    controls.replaceChildren(...parts);
  };

  const paint = () => { paintStatus(); paintControls(); paintMain(); };

  async function playSpin(spin) {
    spinning = true;
    shownSpin = spin;
    landed = null;
    wheel.setSlices(spin.slices);
    paint();
    await wheel.spinTo(spin.landed_id, spin.jitter);
    spinning = false;
    landed = { id: spin.landed_id, by: spin.by };
    tg.haptic.win();
    paint();
  }

  function showAtRest(spin) {
    shownSpin = spin;
    landed = { id: spin.landed_id, by: spin.by };
    wheel.setSlices(spin.slices);
    wheel.showResult(spin.landed_id, spin.jitter);
    paint();
  }

  async function doSpin() {
    if (spinning || hub.disabled) return;
    if (settings.eliminate && landed) settings.excluded.push(landed.id);
    if (remaining().length < 2) {
      landed = null;
      shownSpin = null;
      wheel.setSlices(previewSlices());
      paint();
      return;
    }
    const spin = await act(() => api.spin(id, {
      scope: settings.scope,
      weighted: settings.weighted,
      exclude: settings.excluded,
    }));
    if (spin) await playSpin(spin);
  }

  show(
    backControl(),
    h('h1', {}, poll.question),
    h('div', { class: 'wheel-wrap' }, pointer, canvas, hub),
    status,
    controls,
  );

  wheel.resize();
  const last = poll.last_spin;
  const useLast = last && settings.scope === 'all' && !poll.decision;
  if (useLast && last.age < 8) {
    playSpin(last);
  } else if (useLast) {
    showAtRest(last);
  } else {
    wheel.setSlices(previewSlices().length ? previewSlices() : poll.options.map((o) => ({ id: o.id, label: o.label, weight: 1 })));
    if (poll.decision) wheel.showResult(poll.decision.id, 0.5);
    paint();
  }

  // When someone else spins, everyone watching sees the same spin.
  state.cleanup = liveRefresh(id, (fresh) => {
    poll = fresh;
    const incoming = fresh.last_spin;
    if (!spinning && incoming && incoming.id !== shownSpin?.id && incoming.age < 8) {
      playSpin(incoming);
    } else if (!spinning) {
      if (!shownSpin) wheel.setSlices(previewSlices().length ? previewSlices() : wheel.slices);
      paint();
    }
  });
}

/* ---------- share ---------- */

async function shareScreen(screen) {
  const { id, fresh } = screen;
  if (state.poll?.id !== id) state.poll = await api.poll(id);
  const poll = state.poll;
  const isWheel = poll.mode === 'spin';
  // Without BOT_USERNAME and APP_SHORT_NAME there are no t.me links, so browser
  // testing gets local links that follow the same startapp routing.
  const localLink = (prefix) => `${location.origin}/?startapp=${prefix}_${id}&as=Guest`;
  const linkFor = (key, prefix) => poll.links[key] || localLink(prefix);

  const items = [
    !isWheel && { title: 'Vote link', detail: 'Opens straight on the ballot.', url: linkFor('vote', 'v') },
    !isWheel && { title: 'Results link', detail: 'Opens on the current results.', url: linkFor('results', 'r') },
    { title: 'Wheel link', detail: 'Opens on the wheel and shows the last spin.', url: linkFor('spin', 's') },
  ].filter(Boolean);

  const mainUrl = isWheel ? items[0].url : (poll.decision ? linkFor('results', 'r') : linkFor('vote', 'v'));
  const message = poll.decision ? `${poll.question} Decision: ${poll.decision.label}` : poll.question;

  const send = async () => {
    if (tg.canShareRich() && !poll.decision) {
      try {
        const { id: preparedId } = await api.prepared(id);
        await tg.shareRich(preparedId);
        return;
      } catch { /* the plain share link below still works */ }
    }
    if (!tg.shareLink(mainUrl, message)) {
      await tg.copyText(mainUrl);
      toast('Link copied');
    }
  };

  show(
    backControl(),
    h('h1', {}, fresh ? 'Now send it to the group' : 'Share'),
    h('p', { class: 'hint' }, poll.question),
    items.map((item) => h('div', { class: 'link-row' },
      h('strong', {}, item.title),
      h('span', { class: 'hint' }, item.detail),
      h('code', {}, item.url),
      h('button', {
        class: 'text-btn',
        type: 'button',
        onclick: async () => {
          const ok = await tg.copyText(item.url);
          toast(ok ? 'Link copied' : 'Couldn\'t copy. Select the link and copy it by hand.');
        },
      }, 'Copy link'))),
    h('div', { class: 'stack' },
      fresh && h('button', {
        class: 'btn block',
        type: 'button',
        onclick: () => replace({ name: isWheel ? 'spin' : 'vote', id }),
      }, isWheel ? 'Open the wheel' : 'Cast my vote')),
  );
  tg.setMain('Send to a chat', send);
}

/* ---------- start ---------- */

// startapp values: v_<id> ballot, r_<id> results, s_<id> wheel.
function screenFromStartParam(value) {
  const match = /^([vrs])_([A-Za-z0-9]+)$/.exec(value);
  if (!match) return null;
  const name = { v: 'vote', r: 'results', s: 'spin' }[match[1]];
  return { name, id: match[2] };
}

async function start() {
  tg.setup();
  state.config = await api.config().catch(() => state.config);
  if (!tg.inTelegram && !state.config.dev_mode) {
    show(h('div', { class: 'center' },
      h('h1', {}, 'Open this in Telegram'),
      h('p', { class: 'hint' }, 'This app runs inside Telegram, so it knows who is voting.')));
    return;
  }
  const target = screenFromStartParam(tg.startParam());
  state.stack = [{ name: 'home' }];
  if (target) {
    // A person who already voted lands on results instead of a filled-in ballot.
    if (target.name === 'vote') {
      const poll = await api.poll(target.id).catch(() => null);
      if (poll?.my_ballot) target.name = 'results';
    }
    state.stack.push(target);
  }
  render();
}

start();
