**free
// REGRPTX.RPGLE -- prints the payroll register, every employee and a
// total. Same report, one change: its printer file names PAYOUTQ, a
// queue that shows a file's contents only to the file's owner.

dcl-f payroll keyed;
dcl-f regrptx printer oflind(*inof);

dcl-s tot packed(9:0);

write heading;

setll *loval payroll;
read payroll;
dow not %eof(payroll);
  if *inof;
    write heading;
    *inof = *off;
  endif;
  tot += salary;
  write detail;
  read payroll;
enddo;

write total;
*inlr = *on;
return;
