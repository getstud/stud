// The shared visual workspace exposes one action: show the current design.
const pointSchema = {
  type: 'array', items: {type: 'number'}, minItems: 3, maxItems: 3,
};

export const showInputSchema = {
  type: 'object',
  properties: {
    part_ids: {
      type: 'array', items: {type: 'string', minLength: 1},
      minItems: 1, maxItems: 100, uniqueItems: true,
      description: 'Frame and highlight these exact part IDs, keeping surrounding geometry visible. Omit to show the whole design.',
    },
    region: {
      type: 'object',
      properties: {min: pointSchema, max: pointSchema},
      required: ['min', 'max'], additionalProperties: false,
      description: 'Alternatively frame a bounding region in model inches: X width, Y depth, Z up. Each max must exceed min.',
    },
    view: {type: 'string', enum: ['perspective', 'front', 'side', 'top'], description: 'Camera preset. Defaults to perspective.'},
    expected_revision: {type: 'string', minLength: 1, description: 'If supplied, refuse to show a different model revision.'},
  },
  additionalProperties: false,
  not: {required: ['part_ids', 'region']},
};

export function validateShowInput(input) {
  const fail = message => { throw new Error(message); };
  if (!input || typeof input !== 'object' || Array.isArray(input)) fail('Expected an object.');
  for (const key of Object.keys(input)) {
    if (!Object.hasOwn(showInputSchema.properties, key)) fail(`Unknown input: ${key}`);
  }
  if ('part_ids' in input && 'region' in input) fail('Use part_ids or region, not both.');
  if ('view' in input && !showInputSchema.properties.view.enum.includes(input.view)) fail('Unknown view.');
  if ('expected_revision' in input && (typeof input.expected_revision !== 'string' || !input.expected_revision.length)) fail('Expected a nonempty revision.');
  if ('part_ids' in input) {
    const ids = input.part_ids;
    if (!Array.isArray(ids) || !ids.length || ids.length > 100 ||
        ids.some(id => typeof id !== 'string' || !id.length) || new Set(ids).size !== ids.length) fail('Provide 1–100 unique part IDs.');
  }
  if ('region' in input) {
    const r = input.region;
    if (!r || typeof r !== 'object' || Array.isArray(r) || Object.keys(r).some(k => !['min', 'max'].includes(k))) fail('Invalid region.');
    for (const key of ['min', 'max']) {
      if (!Array.isArray(r[key]) || r[key].length !== 3 || !r[key].every(Number.isFinite)) fail('Region needs finite min/max coordinates.');
    }
    if (r.max.some((v, i) => v <= r.min[i])) fail('Each region max must exceed min.');
  }
  return input;
}

export function createShowTool({loadModel, display}) {
  return {
    name: 'show',
    description: 'Show the current stud design to the user. Refreshes the model, reveals all assemblies, exits exploded display, and frames the whole design or highlights specified parts/a region. Changes only the viewer; does not edit the design or imply user approval. Coordinates are inches, X width, Y depth, Z up.',
    inputSchema: showInputSchema,
    annotations: {readOnlyHint: false},
    execute: async (input = {}, {signal} = {}) => {
      try { validateShowInput(input); }
      catch (error) { return {ok: false, error: {code: 'INVALID_INPUT', message: error.message}}; }
      let model;
      try { model = await loadModel(); if(!model)throw new Error('The model is still being prepared.'); }
      catch (error) { return {ok: false, error: {code: 'MODEL_UNAVAILABLE', message: error.message}}; }
      if (input.expected_revision && input.expected_revision !== model.revision) {
        return {ok: false, error: {code: 'REVISION_CONFLICT', message: 'The current design has a different revision.', actual_revision: model.revision}};
      }
      const missing = (input.part_ids || []).filter(id => !model.parts.some(p => p.id === id));
      if (missing.length) return {ok: false, error: {code: 'PART_NOT_FOUND', message: 'Some requested parts do not exist.', missing_part_ids: missing}};
      signal?.throwIfAborted();
      try { return {ok: true, ...await display(input)}; }
      catch (error) { return {ok: false, error: {code: 'DISPLAY_FAILED', message: error.message}}; }
    },
  };
}

export async function registerShowTool(context, tool) {
  if (typeof context?.registerTool !== 'function') return false;
  await context.registerTool(tool);
  return true;
}
