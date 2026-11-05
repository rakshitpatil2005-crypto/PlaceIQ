import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

async function readPage(name) {
  return readFile(fileURLToPath(new URL(`./${name}.jsx`, import.meta.url)), 'utf8');
}

test('resume upload remains keyboard-accessible and fits narrow screens', async () => {
  const source = await readPage('ResumeUpload');

  assert.match(source, /htmlFor="resume-file"/);
  assert.match(source, /id="resume-file"[\s\S]*?aria-label="Choose a PDF resume"/);
  assert.match(source, /focus-within:ring-4/);
  assert.match(source, /break-all/);
  assert.match(source, /min-h-11 w-full justify-center/);
});

test('roadmap completion keeps a touch-sized accessible status control', async () => {
  const source = await readPage('Roadmap');

  assert.match(source, /onClick=\{\(\) => toggleTask\(wIdx, tIdx\)\}/);
  assert.match(source, /aria-pressed=\{Boolean\(task\.completed\)\}/);
  assert.match(source, /min-h-11 min-w-11/);
  assert.match(source, /min-w-0 flex-1/);
});

test('learning and assessment workflows contain horizontal content and keep controls touch-sized', async () => {
  const [learning, lessonContent, practice, assessment] = await Promise.all([
    readPage('Learning'),
    readFile(fileURLToPath(new URL('../components/LearningLessonContent.jsx', import.meta.url)), 'utf8'),
    readPage('Practice'),
    readPage('Assessment'),
  ]);

  assert.match(learning, /overflow-x-auto[\s\S]*?aria-label="Lesson navigation"/);
  assert.match(learning, /min-h-11 min-w-fit/);
  assert.match(lessonContent, /max-w-full overflow-x-auto/);
  assert.match(practice, /aria-label="Question navigation"[\s\S]*?overflow-x-auto/);
  assert.match(practice, /min-h-11 min-w-11/);
  assert.match(practice, /flex flex-col gap-3[\s\S]*?sm:flex-row/);
  assert.match(assessment, /flex min-h-11 cursor-pointer/);
  assert.match(assessment, /min-h-11 w-full min-w-0/);
});

test('responsive feature pages wrap content and stack controls on small screens', async () => {
  const [dashboard, skillGap, mastery, interview, readiness] = await Promise.all([
    readPage('Dashboard'),
    readPage('SkillGap'),
    readPage('Mastery'),
    readPage('Interview'),
    readPage('Readiness'),
  ]);

  assert.match(dashboard, /break-words/);
  assert.match(skillGap, /min-w-0 sm:min-w-\[240px\]/);
  assert.match(skillGap, /min-h-11 w-full/);
  assert.match(skillGap, /sm:w-auto/);
  assert.match(mastery, /min-w-0 flex-col gap-3 sm:flex-row/);
  assert.match(interview, /min-h-11 w-full rounded-lg/);
  assert.match(interview, /min-h-\[150px\] w-full min-w-0 resize-y/);
  assert.match(readiness, /grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2/);
  assert.match(readiness, /flex flex-col gap-3 sm:flex-row sm:flex-wrap/);
});
