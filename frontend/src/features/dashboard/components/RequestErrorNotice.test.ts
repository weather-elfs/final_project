import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import RequestErrorNotice from './RequestErrorNotice';

test('갱신 실패는 기존 자료 유지 안내와 닫기·재시도 버튼을 제공한다', () => {
  const markup = renderToStaticMarkup(createElement(RequestErrorNotice, { message: 'API 실패 (요청 ID: sample)', hasData: true, busy: false, onRetry: () => {} }));
  assert.match(markup, /최신 자료를 갱신하지 못했습니다/);
  assert.match(markup, /기존 자료는 유지됩니다/);
  assert.match(markup, /aria-label="오류 안내 닫기"/);
  assert.match(markup, /다시 시도/);
  assert.match(markup, /<details><summary>오류 상세 보기<\/summary>/);
  assert.match(markup, /요청 ID: sample/);
});

test('최초 조회 실패는 기존 자료가 있다고 안내하지 않고 조회 중 재시도를 막는다', () => {
  const markup = renderToStaticMarkup(createElement(RequestErrorNotice, { message: 'API 실패', hasData: false, busy: true, onRetry: () => {} }));
  assert.match(markup, /자료를 불러오지 못했습니다/);
  assert.doesNotMatch(markup, /기존 자료는 유지됩니다/);
  assert.match(markup, /disabled="">다시 시도/);
});

test('조회 설정이 없으면 동작하지 않는 재시도 버튼 대신 새로고침을 안내한다', () => {
  const markup = renderToStaticMarkup(createElement(RequestErrorNotice, { message: '설정 실패', hasData: false, busy: false }));
  assert.match(markup, /페이지를 새로고침/);
  assert.doesNotMatch(markup, />다시 시도<\/button>/);
});
