import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
const api='http://127.0.0.1:18000/api';
const base='http://127.0.0.1:15173';
const fix={summary:'Checkout corrected.',location:'Staging build 42.',steps:'Open checkout and press Pay now.'};
async function post(request:APIRequestContext,path:string,data:unknown) {
  const response=await request.post(api+path,{data});expect(response.ok(),`${path}: ${response.status()}`).toBe(true);return response.json();
}
async function fixture(request:APIRequestContext,name:string,customer=false) {
  const project=await post(request,'/projects',{name});
  await post(request,`/projects/${project.id}/members/employee`,{email:'workflow-employee@example.com'});
  const employee=(await (await request.get(`${api}/employees`)).json()).find((row:{name:string})=>row.name==='Workflow Employee');
  let row,token='';
  if(customer) {
    const link=await post(request,`/projects/${project.id}/intake-link`,{});
    const item=await post(request,`/public/intake/${link.token}/submissions`,{client_nonce:`guard-${project.id}-nonce-1234567`,text:'Checkout does not respond.'});
    token=item.access_token;
    await post(request,`/public/submissions/${token}/submit`,{draft_version:item.draft_version});
    row=(await (await request.get(`${api}/feedback`)).json()).find((item:{project_id:string})=>item.project_id===project.id);
  } else row=await post(request,'/feedback',{project_id:project.id,text:'Checkout does not respond.'});
  const report={title:`Report ${name}`,description:'A manually written test brief.',expected_behaviour:null,actual_behaviour:null,reproduction_steps:[],observations:[],hypotheses:[],unknowns:[],questions:[],category:'Functionality',priority:'Medium'};
  expect((await request.put(`${api}/feedback/${row.id}/report`,{data:{version:row.version,report}})).ok()).toBe(true);
  return {project,row,employee,token,report};
}
async function dialogAction(page:Page,action:()=>Promise<unknown>,accept=false,type='confirm') {
  const seen=page.waitForEvent('dialog');
  const done=action();
  const dialog=await seen;
  expect(dialog.type()).toBe(type);
  if(accept)await dialog.accept();else await dialog.dismiss();
  await done;
  return dialog.message();
}

test('next action focuses assignment and retest controls; close, Escape and report switching protect unsent instructions',async({page,request},info)=>{
  const {project,row,employee}=await fixture(request,`Action ${info.project.name}`);
  await page.goto(`/workspace?report=${row.id}`);
  const drawer=page.getByRole('dialog',{name:'Review bug report'});
  const action=drawer.getByRole('region',{name:'Next report action'});
  await expect(action).toContainText('Assign an employee');
  await action.getByRole('button',{name:'Assign employee',exact:true}).click();
  const assigned=drawer.getByLabel('Assigned employee',{exact:true});
  await expect(assigned).toBeFocused();
  expect((await (await request.get(`${api}/feedback/${row.id}/workflow`)).json()).version).toBe(0);
  await assigned.selectOption(employee.id);
  await drawer.getByLabel('Issue status',{exact:true}).selectOption('in_progress');
  await drawer.getByRole('button',{name:'Save progress',exact:true}).click();
  await expect(action.getByRole('button',{name:'Prepare retest',exact:true})).toBeVisible();
  await action.getByRole('button',{name:'Prepare retest',exact:true}).click();
  await expect(drawer.getByLabel('Issue status',{exact:true})).toBeFocused();
  await drawer.getByLabel('Issue status',{exact:true}).selectOption('ready_to_retest');
  await drawer.getByLabel('What changed',{exact:true}).fill(fix.summary);
  await drawer.getByLabel('Where the fix is available',{exact:true}).fill(fix.location);
  await drawer.getByLabel('Steps to retest',{exact:true}).fill(fix.steps);
  const message=await dialogAction(page,()=>drawer.getByRole('button',{name:'Close report',exact:true}).click());
  expect(message).toContain('retest instructions');
  await expect(drawer.getByLabel('Steps to retest',{exact:true})).toHaveValue(fix.steps);
  await dialogAction(page,()=>page.keyboard.press('Escape'));
  await expect(drawer).toBeVisible();
  await drawer.getByRole('button',{name:'Save progress',exact:true}).click();
  await expect(drawer.getByRole('region',{name:'Assignment and progress'}).getByRole('status')).toContainText('Progress saved');
  await action.screenshot({path:`../test-results/${info.project.name}-report-next-action.png`});
  await drawer.getByRole('button',{name:'Close report',exact:true}).click();
  await expect(drawer).toHaveCount(0);
  await page.getByLabel('Filter by project',{exact:true}).selectOption(project.id);
  await page.locator(`[data-report-id="${row.id}"]`).click();
  await expect(drawer.getByLabel('Steps to retest',{exact:true})).toHaveValue(fix.steps);
  await drawer.getByLabel('Steps to retest',{exact:true}).fill('Changed instructions that are not saved.');
  await dialogAction(page,()=>drawer.getByRole('button',{name:'Close report',exact:true}).click(),true);
  expect((await (await request.get(`${api}/feedback/${row.id}/workflow`)).json()).fix_details.steps).toBe(fix.steps);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('report edits and private replies survive cancelled close; action never turns an unsent private note public',async({page,request},info)=>{
  const {row,token}=await fixture(request,`Private draft ${info.project.name}`,true);
  await page.goto(`/workspace?report=${row.id}`);
  const drawer=page.getByRole('dialog',{name:'Review bug report'});
  const action=drawer.getByRole('region',{name:'Next report action'});
  await expect(action).toContainText('Reply to the customer');
  await drawer.getByLabel('Title',{exact:true}).fill('My unsaved report revision');
  await drawer.getByRole('button',{name:'Original feedback',exact:true}).click();
  await drawer.getByRole('button',{name:'Bug report',exact:true}).click();
  await expect(drawer.getByLabel('Title',{exact:true})).toHaveValue('My unsaved report revision');
  const conversation=drawer.getByRole('region',{name:'Report conversation'});
  await conversation.getByLabel('Message visibility',{exact:true}).selectOption('internal');
  await conversation.getByLabel('Private team note',{exact:true}).fill('Private investigation stays private.');
  await action.getByRole('button',{name:'Reply to customer',exact:true}).click();
  await expect(conversation.getByLabel('Private team note',{exact:true})).toBeFocused();
  await expect(conversation.getByLabel('Message visibility',{exact:true})).toHaveValue('internal');
  const message=await dialogAction(page,()=>drawer.getByRole('button',{name:'Close report',exact:true}).click());
  expect(message).toContain('report edits');expect(message).toContain('private note');
  await expect(conversation.getByLabel('Private team note',{exact:true})).toHaveValue('Private investigation stays private.');
  await drawer.getByRole('button',{name:'Save report',exact:true}).click();
  await expect(drawer.getByLabel('Title',{exact:true})).toHaveValue('My unsaved report revision');
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route(`**/api/feedback/${row.id}/messages`,async route=>{
    if(route.request().method()==='POST')await gate;
    await route.continue();
  });
  await conversation.getByRole('button',{name:'Save private note',exact:true}).click();
  await expect(conversation.getByRole('button',{name:'Saving…',exact:true})).toBeDisabled();
  expect(await dialogAction(page,()=>drawer.getByRole('button',{name:'Close report',exact:true}).click(),false,'alert')).toContain('wait');
  await expect(drawer).toBeVisible();
  release();
  await expect(conversation.getByLabel('Private team note',{exact:true})).toHaveValue('');
  expect((await (await request.get(`${api}/public/submissions/${token}/messages`)).json()).length).toBe(0);
  await drawer.getByRole('button',{name:'Close report',exact:true}).click();
  await expect(drawer).toHaveCount(0);
});

test('full-page links and reload warn before losing manual edits; cancellation preserves work and save removes warnings',async({page,request},info)=>{
  await post(request,'/projects',{name:`Navigation guard ${info.project.name}`});
  await page.goto('/workspace');
  await page.getByRole('button',{name:'New feedback',exact:true}).click();
  const field=page.getByLabel('Client feedback',{exact:false});
  await field.fill('Unsaved details must stay in this tab.');
  const link=page.getByRole('link',{name:'Team & account',exact:true});
  if(info.project.name==='mobile')await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await dialogAction(page,()=>link.click());
  if(info.project.name==='mobile')await page.locator('.nav-scrim').click({position:{x:340,y:20}});
  await expect(field).toHaveValue('Unsaved details must stay in this tab.');
  await dialogAction(page,()=>page.evaluate(()=>location.reload()),false,'beforeunload');
  await expect(field).toHaveValue('Unsaved details must stay in this tab.');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Feedback saved');
  if(info.project.name==='mobile')await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await link.click();
  await expect(page).toHaveURL(/\/workspace\/team$/);
});

test('failed customer replies remain protected and a successful send clears the guard',async({browser,request},info)=>{
  const {token}=await fixture(request,`Customer guard ${info.project.name}`,true);
  const context=await browser.newContext({extraHTTPHeaders:{},viewport:info.project.name==='mobile'?{width:390,height:844}:{width:1280,height:900}});
  try{
    const page=await context.newPage();await page.goto(`${base}/s/${token}`);
    const thread=page.getByRole('region',{name:'Report conversation'});
    const reply=thread.getByLabel('Your reply',{exact:true});
    await reply.fill('Please keep my unsent explanation.');
    const link=page.getByRole('link',{name:'Your reports / switch role',exact:true});
    await dialogAction(page,()=>link.click());
    await expect(reply).toHaveValue('Please keep my unsent explanation.');
    await reply.fill('');
    await thread.getByRole('button',{name:'Add screenshots to reply',exact:true}).click();
    const png=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=100;canvas.height=100;return canvas.toDataURL('image/png').split(',')[1];});
    await thread.getByLabel('Choose reply screenshot',{exact:true}).setInputFiles({name:'unsent.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
    await thread.getByLabel('I reviewed this version').check();
    await dialogAction(page,()=>link.click());
    await expect(thread.getByRole('button',{name:'Attach reviewed screenshot',exact:true})).toBeVisible();
    await thread.getByRole('button',{name:'Attach reviewed screenshot',exact:true}).click();
    await expect(thread.getByRole('img',{name:'Reviewed reply screenshot 1',exact:true})).toBeVisible();
    await dialogAction(page,()=>link.click());
    await thread.getByRole('button',{name:'Remove reply screenshot 1',exact:true}).click();
    expect(await page.evaluate(()=>window.dispatchEvent(new Event('beforeunload',{cancelable:true})))).toBe(true);
    await reply.fill('Please keep my unsent explanation.');
    await page.route(`**/api/public/submissions/${token}/messages`,async route=>{
      if(route.request().method()==='POST')await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Test send unavailable.'})});else await route.continue();
    });
    await thread.getByRole('button',{name:'Send reply',exact:true}).click();
    await expect(thread.getByRole('alert')).toBeVisible();
    await dialogAction(page,()=>link.click());
    await expect(reply).toHaveValue('Please keep my unsent explanation.');
    await page.unroute(`**/api/public/submissions/${token}/messages`);
    await thread.getByRole('button',{name:'Send reply',exact:true}).click();
    await expect(reply).toHaveValue('');
    expect(await page.evaluate(()=>window.dispatchEvent(new Event('beforeunload',{cancelable:true})))).toBe(true);
    await reply.fill('This second draft can be left behind.');
    await dialogAction(page,()=>link.click(),true);
    await expect(page).toHaveURL(/\/customer$/);
  }finally{await context.close();}
});


test('Viewer next actions only focus readable sections and cannot modify progress',async({browser,request},info)=>{
  const {project,row}=await fixture(request,`Viewer action ${info.project.name}`);
  await post(request,`/projects/${project.id}/members/employee`,{email:`experience-${info.project.name}@example.test`});
  const context=await browser.newContext({extraHTTPHeaders:{},viewport:info.project.name==='mobile'?{width:390,height:844}:{width:1280,height:900}});
  try{
    await context.addCookies([{name:'bugbrief_employee',value:Buffer.alloc(32,info.project.name==='desktop'?'f':'g').toString('base64url'),url:base}]);
    const account=await(await context.request.get(`${api}/auth/session`)).json();
    expect((await request.patch(`${api}/projects/${project.id}/members/employee/${account.employee.id}`,{data:{role:'viewer',can_delete:false}})).ok()).toBe(true);
    const page=await context.newPage();await page.goto(`${base}/workspace?report=${row.id}`);
    const drawer=page.getByRole('dialog',{name:'Review bug report'});
    const action=drawer.getByRole('region',{name:'Next report action'});
    await expect(action).toContainText(/view-only access/i);
    await action.getByRole('button',{name:'View progress',exact:true}).click();
    await expect(drawer.getByRole('region',{name:'Assignment and progress',exact:true})).toBeFocused();
    await expect(drawer.getByLabel('Assigned employee',{exact:true})).toBeDisabled();
    expect((await(await request.get(`${api}/feedback/${row.id}/workflow`)).json()).version).toBe(0);
    await drawer.getByRole('button',{name:'Close report',exact:true}).click();
    await expect(drawer).toHaveCount(0);
  }finally{await context.close();}
});
